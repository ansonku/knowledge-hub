from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from users.permissions import CanReadLibrary

from . import services, storage
from .models import Category, Document, Tag
from .preview import local_preview_enabled
from .serializers import (
    CategorySerializer,
    DocumentMetadata,
    DocumentSerializer,
    MarkdownEdit,
    NewUpload,
    TagSerializer,
    VersionUpload,
)


def document_list():
    return services.active_documents().select_related("category", "current_version").prefetch_related("tags")


def ids_in_subtree(parent):
    children = {}
    for category_id, parent_id in Category.objects.values_list("id", "parent_id"):
        children.setdefault(parent_id, []).append(category_id)
    pending = [parent]
    descendants = set()
    while pending:
        node = pending.pop()
        if node not in descendants:
            descendants.add(node)
            pending.extend(children.get(node, []))
    return descendants


@never_cache
@api_view(["GET", "POST"])
@permission_classes([CanReadLibrary])
def documents(request):
    if request.method == "POST":
        services.require_editor(request.user)
        form = NewUpload(data=request.data)
        form.is_valid(raise_exception=True)
        document = services.add_upload(request.user, form.validated_data)
        return Response(DocumentSerializer(document).data, status=201)
    query = document_list().order_by("-updated_at", "id")
    filters = request.query_params
    if category := filters.get("category"):
        if category == "uncategorized":
            query = query.filter(category__isnull=True)
        else:
            category_id = serializers.UUIDField().run_validation(category)
            query = query.filter(category_id__in=ids_in_subtree(category_id))
    if document_format := filters.get("file_format"):
        query = query.filter(format=serializers.ChoiceField(Document.Format.values).run_validation(document_format))
    if tag := filters.get("tag"):
        query = query.filter(tags=serializers.UUIDField().run_validation(tag))
    page = serializers.IntegerField(min_value=1, max_value=1_000_000).run_validation(filters.get("page", 1))
    size = 25
    count = query.count()
    return Response({
        "count": count,
        "page": page,
        "page_size": size,
        "results": DocumentSerializer(query[(page - 1) * size:page * size], many=True).data,
        "limits": {"bytes": settings.DOCUMENT_MAX_BYTES, "batch": settings.DOCUMENT_MAX_BATCH},
    })


@never_cache
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([CanReadLibrary])
def document_detail(request, document_id):
    if request.method == "DELETE":
        services.change_document(request.user, document_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == "PATCH":
        services.require_editor(request.user)
        form = DocumentMetadata(data=request.data)
        form.is_valid(raise_exception=True)
        document = services.change_document(request.user, document_id, form.validated_data)
    else:
        document = get_object_or_404(document_list(), pk=document_id)
    return Response({
        **DocumentSerializer(document).data,
        "preview_available": document.format == Document.Format.HTML and local_preview_enabled(request),
    })


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
def new_version(request, document_id, edit=False):
    services.require_editor(request.user)
    form = (MarkdownEdit if edit else VersionUpload)(data=request.data)
    form.is_valid(raise_exception=True)
    document = services.add_upload(request.user, form.validated_data, document_id)
    return Response(DocumentSerializer(document).data, status=201)


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def download(request, document_id):
    document = get_object_or_404(document_list(), pk=document_id)
    version = document.current_version
    if not version or version.path != f"versions/{document.id}/{version.id}":
        raise Http404
    requested = request.query_params.get("version")
    if requested and requested != str(version.pk):
        return Response({"detail": "文件已有新版本，請重新載入。"}, status=status.HTTP_409_CONFLICT)
    try:
        file = (storage.root() / version.path).open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(file, as_attachment=True, filename=version.filename, content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


class TaxonomyViewSet(viewsets.ModelViewSet):
    permission_classes = [CanReadLibrary]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            services.require_editor(request.user)

    def perform_create(self, serializer):
        self.save_object(serializer)

    def perform_update(self, serializer):
        self.save_object(serializer)

    @transaction.atomic
    def save_object(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"name": "名稱已被使用，或相關資料已變更。"}) from None

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise serializers.ValidationError({"detail": "尚有文件或子分類使用此分類。"}) from None


class CategoryViewSet(TaxonomyViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    @transaction.atomic
    def save_object(self, serializer):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["knowledge-hub:categories"])
        if serializer.instance:
            category = get_object_or_404(Category, pk=serializer.instance.pk)
            parent = serializer.validated_data.get("parent", category.parent)
            if parent and parent.pk in ids_in_subtree(category.pk):
                raise serializers.ValidationError({"parent": "不能將分類移至自身或子分類下。"})
            serializer.instance = category
        super().save_object(serializer)


class TagViewSet(TaxonomyViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
