import re
import unicodedata
from codecs import iterdecode
from html.parser import HTMLParser

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, TextField, Value, When
from django.db.models.functions import Coalesce, Left

SKIPPED = {"script", "style", "template", "head"}
BLOCKS = {"p", "div", "article", "section", "li", "br", "td", "th", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "hr"}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED:
            self.hidden.append(tag)
        elif not self.hidden and tag in BLOCKS:
            self.parts.append(" ")
        elif tag == "title" and self.hidden == ["head"]:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in BLOCKS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden or self.hidden == ["head", "title"]:
            self.parts.append(data)


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).replace("\x00", " ")).strip()


def extract(stream, document_format):
    if document_format != "html":
        return normalize(stream.read().decode("utf-8-sig"))
    parser = VisibleText()
    for text in iterdecode(iter(lambda: stream.read(64 * 1024), b""), "utf-8-sig"):
        parser.feed(text)
    parser.close()
    return normalize("".join(parser.parts))


MAX_TERMS = 10


def terms_of(keywords):
    """Search words: whitespace-separated, every one must match (AND). Capped to bound the query."""
    return normalize(keywords).split()[:MAX_TERMS]


def filter_documents(query, keywords):
    terms = terms_of(keywords)
    if not terms:
        return query
    # The bounded PostgreSQL vector handles lexical matches; substring matching also finds unsegmented Chinese.
    query = query.alias(
        full_text=SearchVector(
            "title", Coalesce("category__name", Value("")),
            Left(Coalesce("current_version__search_text", Value("", output_field=TextField())), 120_000),
            config="simple",
        )
    )
    for term in terms:
        query = query.filter(
            Q(title__icontains=term)
            | Q(category__name__icontains=term)
            | Q(tags__name__icontains=term)
            | Q(current_version__search_text__icontains=term)
            | Q(full_text=SearchQuery(term, config="simple")),
        )
    return query.distinct()


# ---- P16a: relevance and match details ---------------------------------------------------------------
# Points per word: a title hit outweighs tags and the collection, which outweigh the body.
TITLE_POINTS, LABEL_POINTS, BODY_POINTS = 8, 3, 1


def hit(condition, points):
    return Case(When(condition, then=Value(points)), default=Value(0), output_field=IntegerField())


def document_relevance(terms, *, prefix=""):
    """Score for Document rows (workspace, reading portal). `prefix` reaches a Document through a relation."""
    from .models import Tag

    score = Value(0, output_field=IntegerField())
    for term in terms:
        tagged = Exists(Tag.objects.filter(document=OuterRef(f"{prefix}pk"), name__icontains=term))
        score = score + hit(Q(**{f"{prefix}title__icontains": term}), TITLE_POINTS) \
            + hit(Q(**{f"{prefix}category__name__icontains": term}) | Q(tagged), LABEL_POINTS) \
            + hit(Q(**{f"{prefix}current_version__search_text__icontains": term}), BODY_POINTS)
    return score


def publication_relevance(terms):
    """Score for ArticlePublication rows: the published title and body only."""
    score = Value(0, output_field=IntegerField())
    for term in terms:
        score = score + hit(Q(title__icontains=term), TITLE_POINTS) + hit(Q(search_text__icontains=term), BODY_POINTS)
    return score


SNIPPET_SOURCE = 200_000  # characters of body text read per result
SNIPPET_WIDTH = 80
SNIPPET_COUNT = 2
# Like the card excerpt's cleanup, but images keep their alt text: it is body text a search can match.
SNIPPET_NOISE = [
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r" \1 "),     # images and videos: keep the alt text
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),         # links keep their text
    (re.compile(r"(^|\s):::\s*gallery\b(?:[ \t]+(?:justified|grid|masonry|vertical|carousel)\b)?|(^|\s):::(?=\s|$)"), " "),  # gallery fences and their layout
    (re.compile(r"(^|\s)(?:```|~~~)[\w+-]*"), " "),          # code fence markers (the code stays searchable)
    (re.compile(r"(^|\s)#{1,6}\s+"), " "),                    # heading markers
    (re.compile(r"(^|\s)(?:>|[-*+]|\d+\.)\s+(?:\[[ xX]\]\s+)?"), " "),  # quotes, list and task markers
    (re.compile(r"\|"), " "),                                # table pipes
    (re.compile(r"(^|\s):?-{3,}:?(?=\s|$)"), " "),            # table separators and rules
    (re.compile(r"[*`~]+"), ""),                             # emphasis and inline code marks
    (re.compile(r"(?<!\w)_+|_+(?!\w)"), ""),                 # _emphasis_, but not snake_case
    (re.compile(r"<[^>]+>"), " "),                           # inline HTML tags
]


def readable_text(text, document_format):
    if document_format == "md":
        for pattern, replacement in SNIPPET_NOISE:
            text = pattern.sub(replacement, text)
    return normalize(text)


def snippets(text, terms, *, count=SNIPPET_COUNT, width=SNIPPET_WIDTH):
    """Up to `count` pieces of `text` around matches, each about `width` characters, with … where cut.
    The first occurrence of every word comes first, so two words far apart both show."""
    if not text or not terms:
        return []
    pattern = re.compile("|".join(re.escape(term) for term in sorted(set(terms), key=len, reverse=True)), re.IGNORECASE)
    found = list(pattern.finditer(text))
    if not found:
        return []
    firsts, seen = [], set()
    for match in found:
        key = match.group(0).casefold()
        if key not in seen:
            seen.add(key)
            firsts.append(match)
    windows = []
    for match in firsts + found:
        if len(windows) == count:
            break
        # Skip matches inside, or just after, a piece already chosen: two pieces should not run into each other.
        if any(start <= match.start() < end + width // 3 for start, end in windows):
            continue
        start = max(0, match.start() - width // 3)
        end = min(len(text), start + width)
        start = max(0, end - width)
        # Do not cut a Latin word in half.
        if start > 0 and text[start - 1].isascii() and text[start - 1].isalnum():
            space = text.find(" ", start, match.start())
            if space != -1:
                start = space + 1
        windows.append((start, end))
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return [("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "") for start, end in merged]


def contains(value, term):
    return term.casefold() in (value or "").casefold()


def match_details(terms, *, title, body, document_format, collection="", tags=()):
    """Which fields matched, and body snippets, for one result. Only text this reader may see is passed in."""
    fields = []
    if any(contains(title, term) for term in terms):
        fields.append("title")
    if any(contains(collection, term) for term in terms):
        fields.append("collection")
    if any(contains(tag, term) for tag in tags for term in terms):
        fields.append("tags")
    text = readable_text(body or "", document_format)
    # Many documents open by repeating their title, which the result already shows.
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" :：-—")
    pieces = snippets(text, [term for term in terms if contains(text, term)])
    if pieces:
        fields.append("body")
    return {"fields": fields, "snippets": pieces}


def document_matches(ids, terms):
    """match_details for Document rows (workspace, reading portal), keyed by document id."""
    from .models import Document

    if not terms or not ids:
        return {}
    rows = Document.objects.filter(pk__in=ids).annotate(
        body=Left(Coalesce("current_version__search_text", Value("", output_field=TextField())), SNIPPET_SOURCE),
    ).values("pk", "title", "format", "category__name", "body")
    tags = {}
    for document_id, name in Document.tags.through.objects.filter(document_id__in=ids).values_list("document_id", "tag__name"):
        tags.setdefault(document_id, []).append(name)
    return {
        row["pk"]: match_details(terms, title=row["title"], body=row["body"], document_format=row["format"],
                                 collection=row["category__name"] or "", tags=tags.get(row["pk"], ()))
        for row in rows
    }


def publication_matches(ids, terms):
    """match_details for published articles: only the published title and body."""
    from .models import ArticlePublication

    if not terms or not ids:
        return {}
    rows = ArticlePublication.objects.filter(document_id__in=ids).annotate(snippet_source=Left("search_text", SNIPPET_SOURCE)) \
        .values("document_id", "title", "format", "snippet_source")
    return {row["document_id"]: match_details(terms, title=row["title"], body=row["snippet_source"], document_format=row["format"])
            for row in rows}
