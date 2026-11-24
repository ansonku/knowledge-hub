import html
import math
import re
from hashlib import sha256
from io import BytesIO

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import Left, Length
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from users.permissions import IsAdmin

from . import activity, search, storage
from .models import ArticlePublication, ArticlePublicationAudit, Document
from .public_html import readable_html


class PublishArticleInput(serializers.Serializer):
    version = serializers.UUIDField()
    title = serializers.CharField(max_length=240, trim_whitespace=False)


def record_action(publication, actor, action):
    ArticlePublicationAudit.objects.create(
        document_id=publication.document_id, version_id=publication.version_id,
        version_number=publication.version.number, title=publication.title, actor=actor, action=action,
    )
    activity.record(
        publication.document_id, actor,
        activity.Action.WITHDRAWN if action == "withdrawn" else activity.Action.PUBLISHED,
        version_number=publication.version.number, republished=action == "republished" or None,
    )


def withdraw_publication(document, actor):
    publication = ArticlePublication.objects.filter(document=document).select_related("version").first()
    if publication:
        record_action(publication, actor, "withdrawn")
        publication.delete()


def publication_body(version, document_format):
    with storage.open_version(version, version.document_id) as source:
        content = source.read()
    if sha256(content).hexdigest() != version.sha256:
        raise ValidationError("版本檔案完整性檢查失敗。")
    body = content.decode("utf-8-sig", errors="replace").replace("\x00", "\ufffd")
    if document_format == Document.Format.HTML:
        body = readable_html(body)
    return body, search.extract(BytesIO(body.encode()), document_format) or ""


def publish(document, actor, data):
    if data["title"] != document.title:
        raise ValidationError("文件標題已變更，請重新開啟發布設定後確認。")
    version = get_object_or_404(document.versions.defer("search_text"), pk=data["version"])
    body, search_text = publication_body(version, document.format)
    publication, created = ArticlePublication.objects.update_or_create(
        document=document,
        defaults={
            "version": version, "title": document.title, "format": document.format, "body": body,
            "search_text": search_text,
        },
    )
    record_action(publication, actor, "published" if created else "republished")


@never_cache
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAdmin])
@transaction.atomic
def manage_publication(request, document_id):
    documents = Document.objects.filter(is_trashed=False)
    if request.method != "GET":
        documents = documents.select_for_update()
    document = get_object_or_404(documents, pk=document_id)
    if request.method == "POST":
        payload = PublishArticleInput(data=request.data)
        payload.is_valid(raise_exception=True)
        publish(document, request.user, payload.validated_data)
    if request.method == "DELETE":
        withdraw_publication(document, request.user)
        return Response(status=204)
    versions = list(document.versions.order_by("-number").values("id", "number"))
    publication = ArticlePublication.objects.filter(document=document).values("title", "version__number").first()
    return Response({"title": document.title, "versions": versions, "publication": publication})


def published_articles():
    return ArticlePublication.objects.filter(document__is_trashed=False)


# ---- Public presentation -------------------------------------------------------------
# Visitors only ever see the publication snapshot plus the name and colour of the article's
# own collection (decision 6 in UI_REDESIGN.md): never descriptions, parents, internal counts,
# authors or tags.

EXCERPT_LENGTH = 120
SAMPLE_LENGTH = 2000
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
MARKDOWN_NOISE = [
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),        # images
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),     # links keep their text
    (re.compile(r"```[^`]*```|~~~.*?~~~"), " "),         # fenced code
    (re.compile(r"(^|\s)#{1,6}\s+"), " "),               # heading markers
    (re.compile(r"(^|\s)(?:>|[-*+]|\d+\.)\s+"), " "),    # quotes and list markers
    (re.compile(r"\|"), " "),                           # table pipes
    (re.compile(r"[*_`~]+"), ""),                       # emphasis and inline code marks
    (re.compile(r"<[^>]+>"), " "),                      # inline HTML tags
]


def summarise(sample, title, document_format):
    text = sample
    if document_format == Document.Format.MARKDOWN:
        for pattern, replacement in MARKDOWN_NOISE:
            text = pattern.sub(replacement, text)
    text = search.normalize(text)
    # Many documents open by repeating their title; the card already shows it.
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" :：-—")
    return text if len(text) <= EXCERPT_LENGTH else text[:EXCERPT_LENGTH].rstrip() + "…"


def reading_minutes(sample, total_length):
    """Estimate from the share of CJK characters: ~400 CJK characters or ~1000 Latin characters a minute."""
    if not total_length:
        return 1
    cjk_share = len(CJK.findall(sample)) / max(1, len(sample))
    per_minute = 1 / (cjk_share / 400 + (1 - cjk_share) / 1000)
    return max(1, math.ceil(total_length / per_minute))


def presented(query):
    return query.annotate(sample=Left("search_text", SAMPLE_LENGTH), text_length=Length("search_text")).values(
        "document_id", "title", "format", "published_at", "sample", "text_length",
        "document__category_id", "document__category__name", "document__category__color",
    )


def collection_of(row):
    if not row["document__category_id"]:
        return None
    return {"id": row["document__category_id"], "name": row["document__category__name"], "color": row["document__category__color"]}


def article_card(row):
    return {
        "document_id": row["document_id"], "title": row["title"], "format": row["format"],
        "published_at": row["published_at"], "excerpt": summarise(row["sample"], row["title"], row["format"]),
        "reading_minutes": reading_minutes(row["sample"], row["text_length"]), "collection": collection_of(row),
    }


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_articles(request):
    articles = published_articles()
    for term in search.normalize(request.query_params.get("q", "")[:240]).split():
        articles = articles.filter(Q(title__icontains=term) | Q(search_text__icontains=term))
    if request.query_params.get("collection"):
        collection = serializers.UUIDField().run_validation(request.query_params["collection"])
        articles = articles.filter(document__category_id=collection)
    paginator = Paginator(presented(articles.order_by("-published_at", "document_id")), 20)
    page = paginator.get_page(request.query_params.get("page"))
    return Response({
        "results": [article_card(row) for row in page], "page": page.number, "pages": paginator.num_pages,
        "count": paginator.count,
    })


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_collections(request):
    rows = (
        published_articles().filter(document__category__isnull=False)
        .values("document__category_id", "document__category__name", "document__category__color")
        .annotate(article_count=Count("pk")).order_by("document__category__name", "document__category_id")
    )
    return Response({"results": [collection_of(row) | {"article_count": row["article_count"]} for row in rows]})


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_article(request, document_id):
    row = get_object_or_404(presented(published_articles()).annotate(body_text=F("body")), pk=document_id)
    siblings = []
    if row["document__category_id"]:
        siblings = list(
            published_articles().filter(document__category_id=row["document__category_id"])
            .order_by("-published_at", "document_id").values("document_id", "title")[:SIBLING_LIMIT]
        )
    return Response({
        "title": row["title"], "format": row["format"], "body": row["body_text"],
        "published_at": row["published_at"], "reading_minutes": reading_minutes(row["sample"], row["text_length"]),
        "collection": collection_of(row), "siblings": siblings,
    })


SIBLING_LIMIT = 200


# ---- Entry pages and their <head> ---------------------------------------------------------
# Nginx serves the SPA's index.html for these responses (X-Accel-Redirect) and swaps its
# <title> for the X-Hub-Head header (sub_filter). The header must be ASCII, so every value is
# HTML-escaped and non-ASCII characters become numeric character references.

SITE_NAME = "Knowledge Hub"
SITE_DESCRIPTION = "團隊成員撰寫並審核後公開的技術規範、操作指南與參考文件。"
HEAD_TEXT_LIMIT = 120


def head_value(text):
    text = search.normalize(text)
    if len(text) > HEAD_TEXT_LIMIT:
        text = text[:HEAD_TEXT_LIMIT].rstrip() + "…"
    return html.escape(text, quote=True).encode("ascii", "xmlcharrefreplace").decode("ascii")


def head_markup(title, description, path, kind):
    title, description = head_value(title), head_value(description)
    url = head_value(settings.PUBLIC_ORIGIN.rstrip("/") + path)
    return "".join((
        f"<title>{title}</title>",
        f'<meta name="description" content="{description}">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{description}">',
        f'<meta property="og:url" content="{url}">',
    ))


def spa_page(head):
    return HttpResponse(headers={"X-Accel-Redirect": "/index.html", "X-Hub-Head": head})


@never_cache
@require_safe
def public_site_page(request):
    return spa_page(head_markup(f"公開文章 · {SITE_NAME}", SITE_DESCRIPTION, "/articles/", "website"))


@never_cache
@require_safe
def public_article_page(request, document_id):
    row = presented(published_articles()).filter(pk=document_id).first()
    if row is None:
        return HttpResponse(status=404)
    description = summarise(row["sample"], row["title"], row["format"]) or SITE_DESCRIPTION
    return spa_page(head_markup(f"{row['title']} · {SITE_NAME}", description, f"/articles/{document_id}/", "article"))
