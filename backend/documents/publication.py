from hashlib import sha256
from io import BytesIO

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
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

from . import search, storage
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


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_articles(request):
    articles = published_articles()
    for term in search.normalize(request.query_params.get("q", "")[:240]).split():
        articles = articles.filter(Q(title__icontains=term) | Q(search_text__icontains=term))
    paginator = Paginator(articles.order_by("-published_at", "document_id").values("document_id", "title"), 20)
    page = paginator.get_page(request.query_params.get("page"))
    return Response({"results": list(page), "page": page.number, "pages": paginator.num_pages})


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_article(request, document_id):
    article = get_object_or_404(published_articles().values("title", "format", "body"), pk=document_id)
    return Response(article)


@never_cache
@require_safe
def public_article_page(request, document_id):
    if not published_articles().filter(pk=document_id).exists():
        return HttpResponse(status=404)
    return HttpResponse(headers={"X-Accel-Redirect": "/index.html"})
