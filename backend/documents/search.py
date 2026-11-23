import re
import unicodedata
from codecs import iterdecode
from html.parser import HTMLParser

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q, TextField, Value
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


def filter_documents(query, keywords):
    terms = normalize(keywords).split()
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
