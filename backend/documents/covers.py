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
    """{document id: {"url", "count"}}: a chosen cover (P22) for any document, otherwise an album's first picture.
    `count` is the album's number of pictures, and None for other documents; an album without pictures has url None."""
    rows = list(Document.objects.filter(pk__in=list(document_ids)).values_list("pk", "presentation", "format", "cover_image_id"))
    albums = [pk for pk, presentation, fmt, _ in rows
              if presentation == Document.Presentation.GALLERY and fmt == Document.Format.MARKDOWN]
    chosen = {pk: cover for pk, _, _, cover in rows if cover}
    pictures = {}
    if albums:
        if public:
            texts = ArticlePublication.objects.filter(document_id__in=albums).annotate(text=Left("body", TEXT_LIMIT)) \
                .values_list("document_id", "text")
        else:
            texts = Document.objects.filter(pk__in=albums).annotate(
                text=Left(Coalesce("current_version__search_text", Value("", output_field=TextField())), TEXT_LIMIT),
            ).values_list("pk", "text")
        pictures = own_pictures(texts)
    found = {}
    for pk in {*albums, *chosen}:
        first = chosen.get(pk) or (pictures.get(pk) or [None])[0]
        found[pk] = {"url": f"/api/images/{first}/thumb/" if first else None,
                     "count": len(pictures.get(pk, [])) if pk in albums else None}
    return found


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
        if "excerpt" in card and cover["count"] is not None:
            card["excerpt"] = album_caption(cover["count"])
    return cards
