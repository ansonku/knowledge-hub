from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.utils import timezone
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from users.lifecycle import audit
from users.models import User
from users.permissions import CanReadLibrary, IsAdmin

from . import search, services, storage, trash
from .models import (
    AUTO_COLLECTION_COLORS, ArticlePublication, Category, Document, DocumentActivity, DocumentView, Favorite, SiteSettings, Tag,
    Version,
)
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
    last_trash = DocumentActivity.objects.filter(
        document_id=OuterRef("pk"), action=DocumentActivity.Action.TRASHED,
    ).order_by("-created_at", "-id")
    documents = Document.objects.filter(is_trashed=True).select_related("category").annotate(
        version_count=Count("versions"), trashed_by_id=Subquery(last_trash.values("actor_id")[:1]),
    ).order_by("-trashed_at", "-updated_at", "id")
    rows = list(documents[(page - 1) * size:page * size])
    actors = {user.pk: user for user in User.objects.filter(pk__in={doc.trashed_by_id for doc in rows} - {None})}
    return Response({
        "count": documents.count(), "page_size": size, "results": [
            {
                "id": doc.pk, "title": doc.title, "format": doc.format,
                # "category" stays the collection name for the legacy trash page; the new page uses category_id.
                "category": doc.category.name if doc.category else None, "category_id": doc.category_id,
                "trashed_at": doc.trashed_at or doc.updated_at, "version_count": doc.version_count,
                "trashed_by": display_name(actors.get(doc.trashed_by_id)),
            }
            for doc in rows
        ],
    })


def display_name(user):
    return (user.display_name or user.username) if user else None


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


class TagMerge(serializers.Serializer):
    sources = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=services.MERGE_LIMIT)
    target = serializers.UUIDField()


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


def next_collection_color():
    """The least used automatic colour, so new collections are easy to tell apart."""
    used = dict(Category.objects.filter(color__in=AUTO_COLLECTION_COLORS).values_list("color").annotate(n=Count("pk")))
    return min(AUTO_COLLECTION_COLORS, key=lambda color: (used.get(color, 0), AUTO_COLLECTION_COLORS.index(color)))


class CategoryViewSet(TaxonomyViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.annotate(document_count=Count("document", filter=Q(document__is_trashed=False)))

    @transaction.atomic
    def save_object(self, serializer):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["knowledge-hub:categories"])
        if not serializer.instance and not serializer.validated_data.get("color"):
            serializer.validated_data["color"] = next_collection_color()
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

    def get_queryset(self):
        return Tag.objects.annotate(document_count=Count("document", filter=Q(document__is_trashed=False)))

    @action(detail=False, methods=["post"], permission_classes=[IsAdmin])
    def merge(self, request):
        payload = TagMerge(data=request.data)
        payload.is_valid(raise_exception=True)
        result = services.merge_tags(request.user, payload.validated_data["sources"], payload.validated_data["target"])
        return Response(result)


# ---- Site settings -------------------------------------------------------------------------------------------

class SiteSettingsInput(serializers.Serializer):
    name = serializers.CharField(max_length=60)
    tagline = serializers.CharField(max_length=160, allow_blank=True)


def site_payload(site, request=None):
    payload = {"name": site.name, "tagline": site.tagline, "notice": site.active_notice()}
    if request is not None and IsAdmin().has_permission(request, None):
        # The editor needs the stored announcement even when it is off or outside its window.
        payload["notice_settings"] = {
            "enabled": site.notice_enabled, "text": site.notice_text, "link": site.notice_link,
            "level": site.notice_level, "starts_at": site.notice_starts_at, "ends_at": site.notice_ends_at,
        }
    return payload


def safe_notice_link(value):
    """Plain http(s) URLs or same-site paths only: never javascript:, data: or protocol-relative links."""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    try:
        URLValidator(schemes=["http", "https"])(value)
    except DjangoValidationError:
        raise serializers.ValidationError("連結必須是 http(s) 網址，或以 / 開頭的站內路徑。") from None
    return value


class NoticeInput(serializers.Serializer):
    enabled = serializers.BooleanField()
    text = serializers.CharField(max_length=120, allow_blank=True)
    link = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    level = serializers.ChoiceField(SiteSettings.NoticeLevel.values)
    starts_at = serializers.DateTimeField(allow_null=True, required=False, default=None)
    ends_at = serializers.DateTimeField(allow_null=True, required=False, default=None)

    def validate_text(self, value):
        # Plain text on one line; the banner never renders markup.
        return " ".join(value.split())

    def validate_link(self, value):
        return safe_notice_link(value)

    def validate(self, data):
        if data["enabled"] and not data["text"]:
            raise serializers.ValidationError({"text": "開啟公告時必須填寫內容。"})
        if data["starts_at"] and data["ends_at"] and data["ends_at"] <= data["starts_at"]:
            raise serializers.ValidationError({"ends_at": "結束時間必須晚於開始時間。"})
        return data


@never_cache
@api_view(["PUT"])
@permission_classes([IsAdmin])
def site_notice(request):
    """P6c: Admins edit the announcement banner shown on every page."""
    payload = NoticeInput(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    with transaction.atomic():
        site, _ = SiteSettings.objects.select_for_update().get_or_create(pk=1)
        was_enabled = site.notice_enabled
        site.notice_enabled, site.notice_text, site.notice_link = data["enabled"], data["text"], data["link"]
        site.notice_level, site.notice_starts_at, site.notice_ends_at = data["level"], data["starts_at"], data["ends_at"]
        site.notice_updated_at = timezone.now()
        site.updated_by = request.user
        site.save()
        action = ("site_notice_enabled" if data["enabled"] else "site_notice_disabled") if was_enabled != data["enabled"] else "site_notice_updated"
        audit(action, request.user, actor=request.user)
    return Response(site_payload(site, request))


@never_cache
@api_view(["GET", "PATCH"])
@permission_classes([AllowAny])
def site_settings(request):
    """Anyone can read the site name and tagline (the public site shows them); only Admins change them."""
    if request.method == "PATCH":
        if not IsAdmin().has_permission(request, None):
            raise PermissionDenied
        payload = SiteSettingsInput(data=request.data)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            site, _ = SiteSettings.objects.select_for_update().get_or_create(pk=1)
            site.name = payload.validated_data["name"].strip() or SiteSettings.DEFAULT_NAME
            site.tagline = payload.validated_data["tagline"].strip()
            site.updated_by = request.user
            site.save()
        return Response(site_payload(site, request))
    return Response(site_payload(SiteSettings.current(), request))

