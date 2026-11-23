from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.utils import timezone
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from users.permissions import CanReadLibrary, IsAdmin

from . import search, services, storage, trash
from .models import ArticlePublication, Category, Document, DocumentActivity, DocumentView, Favorite, Tag, Version
from .preview import local_preview_enabled
from .serializers import (
    ActivitySerializer,
    BulkChange,
    CategorySerializer,
    DocumentListSerializer,
    DocumentMetadata,
    DocumentSerializer,
    MarkdownEdit,
    NewUpload,
    RestoreVersion,
    TagSerializer,
    VersionSerializer,
    VersionUpload,
)


def document_list():
    return (
        services.active_documents()
        .select_related("category", "current_version__created_by", "current_version__restored_from")
        .defer("current_version__search_text", "current_version__restored_from__search_text")
        .prefetch_related("tags")
    )


def with_member_fields(query, user):
    """Annotate list fields that depend on the viewer (favourites) or on publication state."""
    return query.annotate(
        is_public=Exists(ArticlePublication.objects.filter(document_id=OuterRef("pk"))),
        published_version=Subquery(
            ArticlePublication.objects.filter(document_id=OuterRef("pk")).values("version__number")[:1],
        ),
        is_favorite=Exists(Favorite.objects.filter(document_id=OuterRef("pk"), user=user)),
    )


ORDERING = {
    "-updated_at": ("-updated_at", "id"),
    "updated_at": ("updated_at", "id"),
    "title": ("title", "id"),
    "-title": ("-title", "id"),
}


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
    filters = request.query_params
    ordering = serializers.ChoiceField(list(ORDERING)).run_validation(filters.get("ordering", "-updated_at"))
    query = with_member_fields(document_list(), request.user).order_by(*ORDERING[ordering])
    if keywords := filters.get("q"):
        keywords = serializers.CharField(max_length=240, allow_blank=True).run_validation(keywords)
        query = search.filter_documents(query, keywords)
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
    if visibility := filters.get("visibility"):
        visibility = serializers.ChoiceField(["public", "private", "lagging"]).run_validation(visibility)
        if visibility == "private":
            query = query.filter(is_public=False)
        elif visibility == "public":
            query = query.filter(is_public=True)
        else:
            query = query.filter(published_version__lt=F("current_version__number"))
    if filters.get("favorite") in ("1", "true"):
        query = query.filter(is_favorite=True)
    page = serializers.IntegerField(min_value=1, max_value=1_000_000).run_validation(filters.get("page", 1))
    size = 25
    count = query.count()
    return Response({
        "count": count,
        "page": page,
        "page_size": size,
        "results": DocumentListSerializer(query[(page - 1) * size:page * size], many=True).data,
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
        document = get_object_or_404(with_member_fields(document_list(), request.user), pk=document_id)
    payload = DocumentSerializer(document).data
    if request.method == "GET":
        payload |= {
            "is_favorite": document.is_favorite, "is_public": document.is_public,
            "published_version": document.published_version,
        }
    return Response({
        **payload,
        "preview_available": document.format == Document.Format.HTML and local_preview_enabled(request),
    })


# ---- Member workspace: favourites, recent views, activity, bulk changes ----

RECENT_LIMIT = 50


@never_cache
@api_view(["PUT", "DELETE"])
@permission_classes([CanReadLibrary])
def favorite(request, document_id):
    document = get_object_or_404(services.active_documents(), pk=document_id)
    if request.method == "PUT":
        Favorite.objects.get_or_create(user=request.user, document=document)
    else:
        Favorite.objects.filter(user=request.user, document=document).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
@transaction.atomic
def record_view(request, document_id):
    document = get_object_or_404(services.active_documents(), pk=document_id)
    DocumentView.objects.update_or_create(user=request.user, document=document, defaults={"viewed_at": timezone.now()})
    stale = DocumentView.objects.filter(user=request.user).order_by("-viewed_at").values_list("pk", flat=True)[RECENT_LIMIT:]
    DocumentView.objects.filter(pk__in=list(stale)).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def recent(request):
    limit = serializers.IntegerField(min_value=1, max_value=RECENT_LIMIT).run_validation(request.query_params.get("limit", 10))
    views = DocumentView.objects.filter(user=request.user, document__is_trashed=False).order_by("-viewed_at")[:limit]
    viewed = {view.document_id: view.viewed_at for view in views}
    documents = {doc.pk: doc for doc in with_member_fields(document_list(), request.user).filter(pk__in=viewed)}
    ordered = [documents[pk] for pk in viewed if pk in documents]
    return Response({"results": [
        {**DocumentListSerializer(doc).data, "viewed_at": viewed[doc.pk]} for doc in ordered
    ]})


def activity_page(request, query):
    page = serializers.IntegerField(min_value=1, max_value=10_000).run_validation(request.query_params.get("page", 1))
    size = 20
    rows = list(query.select_related("actor", "document").filter(document__is_trashed=False)[(page - 1) * size:page * size + 1])
    return Response({"page": page, "has_more": len(rows) > size, "results": ActivitySerializer(rows[:size], many=True).data})


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def document_activity(request, document_id):
    get_object_or_404(services.active_documents(), pk=document_id)
    return activity_page(request, DocumentActivity.objects.filter(document_id=document_id))


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def activity_feed(request):
    scope = serializers.ChoiceField(["all", "mine", "publish"]).run_validation(request.query_params.get("scope", "all"))
    query = DocumentActivity.objects.all()
    if scope == "mine":
        query = query.filter(actor=request.user)
    elif scope == "publish":
        query = query.filter(action__in=[DocumentActivity.Action.PUBLISHED, DocumentActivity.Action.WITHDRAWN])
    return activity_page(request, query)


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
def bulk(request):
    services.require_editor(request.user)
    form = BulkChange(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    count = services.bulk_change(
        request.user, data["ids"], data["action"], category=data.get("category"), tags=data.get("tags", []),
    )
    return Response({"count": count})


@never_cache
@api_view(["GET", "POST"])
@permission_classes([CanReadLibrary])
def new_version(request, document_id, edit=False):
    if request.method in ("GET", "HEAD"):
        if edit:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return version_history(request, document_id)
    services.require_editor(request.user)
    form = (MarkdownEdit if edit else VersionUpload)(data=request.data)
    form.is_valid(raise_exception=True)
    document = services.add_upload(request.user, form.validated_data, document_id)
    return Response(DocumentSerializer(document).data, status=201)


def document_versions(document_id):
    return Version.objects.filter(document_id=document_id, document__is_trashed=False).select_related(
        "created_by", "restored_from",
    ).defer("search_text", "restored_from__search_text")


def version_history(request, document_id):
    current = get_object_or_404(services.active_documents().only("current_version"), pk=document_id).current_version_id
    page = serializers.IntegerField(min_value=1, max_value=1_000_000).run_validation(request.query_params.get("page", 1))
    size = 25
    query = document_versions(document_id).order_by("-number")
    return Response({
        "current": current, "count": query.count(), "page_size": size,
        "results": VersionSerializer(query[(page - 1) * size:page * size], many=True).data,
    })


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def version_detail(request, document_id, version_id):
    return Response(VersionSerializer(get_object_or_404(document_versions(document_id), pk=version_id)).data)


def version_attachment(version, document_id):
    file = storage.open_version(version, document_id)
    response = FileResponse(file, as_attachment=True, filename=version.filename, content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def download(request, document_id):
    document = get_object_or_404(document_list(), pk=document_id)
    version = document.current_version
    if not version:
        raise Http404
    requested = request.query_params.get("version")
    if requested and requested != str(version.pk):
        return Response({"detail": "文件已有新版本，請重新載入。"}, status=status.HTTP_409_CONFLICT)
    return version_attachment(version, document_id)


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def download_version(request, document_id, version_id):
    return version_attachment(get_object_or_404(document_versions(document_id), pk=version_id), document_id)


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
def restore_version(request, document_id, version_id):
    services.require_editor(request.user)
    form = RestoreVersion(data=request.data)
    form.is_valid(raise_exception=True)
    document = services.restore_version(request.user, document_id, version_id, **form.validated_data)
    return Response(DocumentSerializer(document).data, status=201)


class PermanentDeletion(serializers.Serializer):
    title = serializers.CharField(max_length=240, trim_whitespace=False)
    confirm = serializers.BooleanField()


@never_cache
@api_view(["GET"])
@permission_classes([CanReadLibrary])
def trash_list(request):
    services.require_editor(request.user)
    page = serializers.IntegerField(min_value=1, max_value=1_000_000).run_validation(request.query_params.get("page", 1))
    size = 25
    documents = Document.objects.filter(is_trashed=True).select_related("category").annotate(
        version_count=Count("versions"),
    ).order_by("-trashed_at", "-updated_at", "id")
    return Response({
        "count": documents.count(), "page_size": size, "results": [
            {
                "id": doc.pk, "title": doc.title, "format": doc.format,
                "category": doc.category.name if doc.category else None,
                "trashed_at": doc.trashed_at or doc.updated_at, "version_count": doc.version_count,
            }
            for doc in documents[(page - 1) * size:page * size]
        ],
    })


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
def restore_trashed_document(request, document_id):
    document = trash.restore_document(request.user, document_id)
    return Response(DocumentSerializer(document).data)


@never_cache
@api_view(["POST"])
@permission_classes([IsAdmin])
def delete_trashed_document(request, document_id):
    confirmation = PermanentDeletion(data=request.data)
    confirmation.is_valid(raise_exception=True)
    trash.queue_permanent_deletion(request.user, document_id, **confirmation.validated_data)
    if not trash.finish_permanent_deletion(document_id):
        return Response({"detail": "已永久移除文件紀錄，檔案清理等待重試。"}, status=202)
    return Response(status=status.HTTP_204_NO_CONTENT)


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

    def get_queryset(self):
        return Category.objects.annotate(document_count=Count("document", filter=Q(document__is_trashed=False)))

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
