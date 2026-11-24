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
from .models import ArticlePublication, ArticlePublicationAudit, Category, Document, FeaturedArticle, SiteSettings
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
        # Withdrawn (or trashed) articles leave the public home's featured list for good (P6b).
        if FeaturedArticle.objects.filter(document=document).delete()[0]:
            activity.record(document.pk, actor, activity.Action.UNFEATURED, automatic=True)


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
# Visitors only ever see the publication snapshot plus the names and colours of the collections
# on the path to a published article (decision 6, revised in P5b): never descriptions, internal
# counts, collections with no published article in their subtree, authors or tags.

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
    (re.compile(r"(^|\s):?-{3,}:?(?=\s|$)"), " "),       # table separator cells and rules (---, :---:)
    (re.compile(r"[*`~]+"), ""),                        # emphasis and inline code marks
    (re.compile(r"(?<!\w)_+|_+(?!\w)"), ""),            # _emphasis_, but not snake_case words
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


def category_index():
    """All collections as {id: (name, colour, parent_id)}; the table is small."""
    return {pk: (name, color, parent) for pk, name, color, parent in Category.objects.values_list("pk", "name", "color", "parent_id")}


def path_of(category_id, index):
    """Root-to-leaf [{id, name, color}] for a collection, or [] when uncategorised."""
    path, seen = [], set()
    while category_id and category_id in index and category_id not in seen:
        seen.add(category_id)
        name, color, parent = index[category_id]
        path.insert(0, {"id": category_id, "name": name, "color": color})
        category_id = parent
    return path


def subtree_ids(category_id, index):
    found, frontier = {category_id}, [category_id]
    while frontier:
        current = frontier.pop()
        children = [pk for pk, (_, _, parent) in index.items() if parent == current and pk not in found]
        found.update(children)
        frontier.extend(children)
    return found


def public_tree(index):
    """Collections holding published articles plus their ancestors, depth first by name."""
    direct = dict(
        published_articles().filter(document__category__isnull=False)
        .values_list("document__category_id").annotate(count=Count("pk"))
    )
    return collection_tree(direct, index)


def collection_tree(direct, index):
    """Collections with articles ({id: count}) plus their ancestors, depth first by name.

    Each node: id, name, color, parent, depth, article_count (its own) and total_count (its subtree).
    """
    visible = set()
    for category_id in direct:
        visible.update(node["id"] for node in path_of(category_id, index))
    children = {}
    for pk in visible:
        children.setdefault(index[pk][2], []).append(pk)
    nodes = []

    def walk(parent, depth):
        total = 0
        for pk in sorted(children.get(parent, []), key=lambda key: (index[key][0].lower(), str(key))):
            node = {"id": pk, "name": index[pk][0], "color": index[pk][1], "parent": parent,
                    "depth": depth, "article_count": direct.get(pk, 0)}
            nodes.append(node)
            node["total_count"] = node["article_count"] + walk(pk, depth + 1)
            total += node["total_count"]
        return total

    walk(None, 0)
    return nodes


def collection_of(row):
    if not row["document__category_id"]:
        return None
    return {"id": row["document__category_id"], "name": row["document__category__name"], "color": row["document__category__color"]}


def article_card(row, index):
    return {
        "path": path_of(row["document__category_id"], index),
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
    index = category_index()
    if request.query_params.get("collection"):
        collection = serializers.UUIDField().run_validation(request.query_params["collection"])
        # A collection's page lists its sub-collections' articles too.
        articles = articles.filter(document__category_id__in=subtree_ids(collection, index))
    paginator = Paginator(presented(articles.order_by("-published_at", "document_id")), 20)
    page = paginator.get_page(request.query_params.get("page"))
    return Response({
        "results": [article_card(row, index) for row in page], "page": page.number, "pages": paginator.num_pages,
        "count": paginator.count,
    })


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_collections(request):
    return Response({"results": public_tree(category_index())})


NAV_LIMIT = 1000


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_nav(request):
    """Everything the public site's side navigation needs in one request: the collection tree and
    the titles of published articles (newest first)."""
    index = category_index()
    articles = [
        {"document_id": pk, "title": title, "collection_id": category, "published_at": published}
        for pk, title, category, published in published_articles().order_by("-published_at", "document_id")
        .values_list("document_id", "title", "document__category_id", "published_at")[:NAV_LIMIT]
    ]
    return Response({"collections": public_tree(index), "articles": articles})


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
        "collection": collection_of(row), "path": path_of(row["document__category_id"], category_index()),
        "siblings": siblings,
    })


SIBLING_LIMIT = 200


# ---- Entry pages and their <head> ---------------------------------------------------------
# Nginx serves the SPA's index.html for these responses (X-Accel-Redirect) and swaps its
# <title> for the X-Hub-Head header (sub_filter). The header must be ASCII, so every value is
# HTML-escaped and non-ASCII characters become numeric character references.

HEAD_TEXT_LIMIT = 120


def head_value(text):
    text = search.normalize(text)
    if len(text) > HEAD_TEXT_LIMIT:
        text = text[:HEAD_TEXT_LIMIT].rstrip() + "…"
    return html.escape(text, quote=True).encode("ascii", "xmlcharrefreplace").decode("ascii")


def head_markup(title, description, path, kind, site_name):
    title, description = head_value(title), head_value(description)
    url = head_value(settings.PUBLIC_ORIGIN.rstrip("/") + path)
    return "".join((
        f"<title>{title}</title>",
        f'<meta name="description" content="{description}">',
        f'<meta property="og:site_name" content="{head_value(site_name)}">',
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
    site = SiteSettings.current()
    return spa_page(head_markup(site.name, site.tagline or site.name, "/articles/", "website", site.name))


@never_cache
@require_safe
def public_article_page(request, document_id):
    row = presented(published_articles()).filter(pk=document_id).first()
    if row is None:
        return HttpResponse(status=404)
    site = SiteSettings.current()
    description = summarise(row["sample"], row["title"], row["format"]) or site.tagline or site.name
    return spa_page(head_markup(f"{row['title']} · {site.name}", description, f"/articles/{document_id}/", "article", site.name))
