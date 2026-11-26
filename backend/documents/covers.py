"""P21b: album articles show a cover — the first of their own pictures, as a thumbnail — and how many there are.

Public pages read the published body only, so visitors never see a picture that is not published;
the reading portal reads the current version. Ordinary articles get nothing.
"""
from uuid import UUID

from django.db.models import TextField, Value
from django.db.models.functions import Coalesce, Left

from .models import ArticlePublication, Document, DocumentImage

TEXT_LIMIT = 200_000


def own_pictures(texts):
    """{document id: [image ids in order of first appearance]} — only the document's own pictures."""
    from .images import REFERENCE  # images → services → publication → covers: import when used
    wanted = {doc: list(dict.fromkeys(match.lower() for match in REFERENCE.findall(text or ""))) for doc, text in texts}
    owned = set(DocumentImage.objects.filter(pk__in={pk for ids in wanted.values() for pk in ids})
                .values_list("document_id", "pk"))
    return {doc: [pk for pk in ids if (doc, UUID(pk)) in owned] for doc, ids in wanted.items()}


def covers(document_ids, *, public):
    """{document id: {"url", "count"}} for the album articles among `document_ids` (count may be 0, url then None)."""
    albums = list(Document.objects.filter(pk__in=list(document_ids), presentation=Document.Presentation.GALLERY,
                                          format=Document.Format.MARKDOWN).values_list("pk", flat=True))
    if not albums:
        return {}
    if public:
        texts = ArticlePublication.objects.filter(document_id__in=albums).annotate(text=Left("body", TEXT_LIMIT)) \
            .values_list("document_id", "text")
    else:
        texts = Document.objects.filter(pk__in=albums).annotate(
            text=Left(Coalesce("current_version__search_text", Value("", output_field=TextField())), TEXT_LIMIT),
        ).values_list("pk", "text")
    pictures = own_pictures(texts)
    return {doc: {"url": f"/api/images/{ids[0]}/thumb/" if ids else None, "count": len(ids)} for doc, ids in pictures.items()}


def album_caption(count):
    return f"相簿 · {count} 張圖片" if count else "相簿"


def add_covers(cards, *, public, key="document_id"):
    """Give album cards their cover and a caption instead of the opening lines (which are gallery syntax)."""
    found = covers([card[key] for card in cards], public=public)
    for card in cards:
        cover = found.get(card[key])
        if cover is None:
            continue
        card["cover"] = cover
        if "excerpt" in card:
            card["excerpt"] = album_caption(cover["count"])
    return cards
