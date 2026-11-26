"""Member reading portal (/read/): the public portal's layout over every document a member can read.

All endpoints require CanReadLibrary. Responses reuse the public card / article shapes so the same
Vue components render both, plus `public` (is the document published?) and `updated_at`. HTML is
returned as the same sanitised, script-free reading copy the public site uses (rendered in an
iframe with sandbox=""), never the raw upload.
"""
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import Left, Length
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from users.permissions import CanReadLibrary

from . import search
from .image_sizes import version_image_sizes
from .links import readable_targets
from .models import ArticlePublication, Document
from .publication import (
    SAMPLE_LENGTH, category_index, collection_tree, path_of, publication_body, reading_minutes, subtree_ids, summarise,
)
from .services import active_documents

NAV_LIMIT = 2000
PAGE_SIZE = 20


def readable():
    return active_documents().annotate(
        public=Exists(ArticlePublication.objects.filter(document=OuterRef("pk"))),
    )


def collection_ref(category_id, index):
    if not category_id or category_id not in index:
        return None
    name, color, _ = index[category_id]
    return {"id": category_id, "name": name, "color": color}


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def read_nav(request):
    index = category_index()
    direct = dict(
        active_documents().filter(category__isnull=False).values_list("category_id").annotate(count=Count("pk"))
    )
    articles = [
        {"document_id": pk, "title": title, "collection_id": category, "updated_at": updated}
        for pk, title, category, updated in active_documents().order_by("-updated_at", "pk")
        .values_list("pk", "title", "category_id", "updated_at")[:NAV_LIMIT]
    ]
    return Response({"collections": collection_tree(direct, index), "articles": articles})


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def read_articles(request):
    index = category_index()
    documents = search.filter_documents(readable(), request.query_params.get("q", "")[:240])
    if request.query_params.get("collection"):
        collection = serializers.UUIDField().run_validation(request.query_params["collection"])
        documents = documents.filter(category_id__in=subtree_ids(collection, index))
    rows = documents.order_by("-updated_at", "pk").annotate(
        sample=Left("current_version__search_text", SAMPLE_LENGTH), text_length=Length("current_version__search_text"),
    ).values("pk", "title", "format", "updated_at", "category_id", "public", "sample", "text_length")
    paginator = Paginator(rows, PAGE_SIZE)
    page = paginator.get_page(request.query_params.get("page"))
    return Response({
        "results": [
            {
                "document_id": row["pk"], "title": row["title"], "format": row["format"], "updated_at": row["updated_at"],
                "excerpt": summarise(row["sample"] or "", row["title"], row["format"]),
                "reading_minutes": reading_minutes(row["sample"] or "", row["text_length"] or 0),
                "collection": collection_ref(row["category_id"], index), "path": path_of(row["category_id"], index),
                "public": row["public"],
            }
            for row in page
        ],
        "page": page.number, "pages": paginator.num_pages, "count": paginator.count,
    })


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def read_article(request, document_id):
    document = get_object_or_404(readable().select_related("current_version"), pk=document_id)
    version = document.current_version
    body, text = publication_body(version, document.format)
    index = category_index()
    return Response({
        "title": document.title, "format": document.format, "body": body, "updated_at": document.updated_at,
        "version_number": version.number, "reading_minutes": reading_minutes(text[:SAMPLE_LENGTH], len(text)),
        "collection": collection_ref(document.category_id, index), "path": path_of(document.category_id, index),
        "public": document.public, "siblings": [],
        "image_sizes": version_image_sizes(version) if document.format == Document.Format.MARKDOWN else {},
        "presentation": document.presentation, "gallery_layout": document.gallery_layout,
        "linked_documents": readable_targets(version) if document.format == Document.Format.MARKDOWN else [],
    })
