import logging
import re
import uuid
from pathlib import Path

from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from users.models import User
from users.permissions import has_role

from . import activity, quota, search, storage
from .models import ArticlePublication, Document, DocumentImage, DocumentTrashAudit, Tag, Version, VersionRestoreAudit
from .publication import withdraw_publication


logger = logging.getLogger(__name__)

STORAGE_LOCK_KEY = "knowledge-hub:document-files"


class DuplicateContent(APIException):
    status_code = 409
    default_detail = "內容重複，請確認是否仍要儲存。"
    default_code = "duplicate_content"


class VersionConflict(APIException):
    status_code = 409
    default_detail = "文件已有新版本。請保留草稿並重新載入最新版本。"
    default_code = "version_conflict"


def require_editor(actor):
    if not has_role(actor, User.Role.ADMIN, User.Role.EDITOR):
        raise PermissionDenied()


def active_documents():
    return Document.objects.filter(is_trashed=False)


def add_upload(actor, data, document_id=None):
    require_editor(actor)
    upload = data["file"]
    base_version = data.get("base_version")
    filename = upload.name
    suffix = Path(upload.name).suffix.lower().removeprefix(".")
    if suffix not in Document.Format.values:
        raise ValidationError({"file": "只接受 .html 或 .md 檔案。"})
    if base_version is None:
        # P23: uploads count against the limit; saving Markdown text in the editor does not (too small to matter).
        quota.check_space(upload.size)
    with storage.stage(upload) as (temporary, sha256, size), transaction.atomic():
        lock_storage(sha256)
        if document_id is None:
            duplicate = Version.objects.filter(sha256=sha256, document__is_trashed=False).exists()
            if duplicate and not data["force"]:
                raise DuplicateContent()
            document = Document.objects.create(
                title=data.get("title") or Path(upload.name).stem[:240] or upload.name[:240],
                format=suffix, category=data.get("category"), created_by=actor,
            )
            document.tags.set(data.get("tags", []))
            number = 1
        else:
            document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
            if document.format != suffix:
                raise ValidationError({"file": "新版本必須維持原始文件格式。"})
            current = Version.objects.defer("search_text").get(pk=document.current_version_id)
            if base_version is not None:
                if document.format != Document.Format.MARKDOWN:
                    raise ValidationError({"file": "只支援編輯 Markdown 文件。"})
                if current.pk != base_version:
                    raise VersionConflict()
                filename = current.filename
            if current.sha256 == sha256 and not data["force"]:
                raise DuplicateContent()
            number = current.number + 1

        publish_version(
            document, actor, temporary, sha256, size, number, filename,
            data.get("note", ""), "markdown_edit" if base_version else "upload",
        )
    return document


# Path separators, characters Windows refuses in file names, and control characters.
UNSAFE_FILENAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')


def markdown_filename(title):
    """The file name a written document downloads as."""
    name = UNSAFE_FILENAME.sub(" ", title)
    name = " ".join(name.split()).strip(" .")[:200]
    return f"{name or 'document'}.md"


def create_markdown(actor, data):
    """Create a Markdown document whose v1 is just its title, ready to be written in the editor.

    No duplicate-content check: new documents with the same title start out identical.
    """
    require_editor(actor)
    title = " ".join(data["title"].split())
    if not title:
        raise ValidationError({"title": "請輸入標題。"})
    filename = markdown_filename(title)
    upload = SimpleUploadedFile(filename, f"# {title}\n\n".encode())
    with storage.stage(upload) as (temporary, sha256, size), transaction.atomic():
        lock_storage(sha256)
        document = Document.objects.create(
            title=title, format=Document.Format.MARKDOWN, category=data.get("category"), created_by=actor,
        )
        document.tags.set(data.get("tags", []))
        publish_version(document, actor, temporary, sha256, size, 1, filename, "", "create")
    return document


@transaction.atomic
def change_document(actor, document_id, data=None):
    require_editor(actor)
    document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
    if data is None:
        withdraw_publication(document, actor)
        document.is_trashed = True
        document.trashed_at = timezone.now()
        document.save(update_fields=["is_trashed", "trashed_at", "updated_at"])
        record_trash_action(document, actor, "trashed")
        activity.record(document.pk, actor, activity.Action.TRASHED)
    else:
        before = activity.metadata_snapshot(document)
        if "presentation" in data and data["presentation"] != document.presentation \
                and document.format != Document.Format.MARKDOWN:
            raise ValidationError({"presentation": "只有 Markdown 文件可以使用相簿模式。"})
        if "cover_image" in data:
            # Only this document's own pictures (P22).
            cover = data["cover_image"]
            if cover is not None and not DocumentImage.objects.filter(pk=cover, document=document).exists():
                raise ValidationError({"cover_image": "封面只能使用這份文件的圖片。"})
            document.cover_image_id = cover
        fields = [field for field in ("title", "category", "presentation", "gallery_layout") if field in data]
        for field in fields:
            setattr(document, field, data[field])
        if "tags" in data:
            document.tags.set(data["tags"])
        document.save(update_fields=[*fields, *(["cover_image"] if "cover_image" in data else []), "updated_at"])
        activity.record_metadata(document, actor, before)
    return document


BULK_LIMIT = 100


@transaction.atomic
def bulk_change(actor, document_ids, action, *, category=None, tags=(), set_category=True):
    """Apply one change to several documents atomically, each through change_document."""
    require_editor(actor)
    ids = list(dict.fromkeys(document_ids))
    if not ids or len(ids) > BULK_LIMIT:
        raise ValidationError({"ids": f"請選擇 1 至 {BULK_LIMIT} 份文件。"})
    # Lock in a stable order so concurrent bulk requests cannot deadlock.
    found = set(active_documents().select_for_update().filter(pk__in=ids).order_by("pk").values_list("pk", flat=True))
    if missing := [str(pk) for pk in ids if pk not in found]:
        raise ValidationError({"ids": "部分文件已不存在或已移入回收桶，請重新整理後再試。", "missing": missing})
    tag_ids = {tag.pk for tag in tags}
    for document_id in ids:
        if action == "trash":
            change_document(actor, document_id)
        elif action == "move":
            change_document(actor, document_id, {"category": category})
        elif action == "organize":
            # One change per document, so its activity shows the collection and the tags together.
            document = Document.objects.get(pk=document_id)
            changes = {}
            if set_category and document.category_id != (category.pk if category else None):
                changes["category"] = category
            current = set(document.tags.values_list("pk", flat=True))
            if tag_ids - current:
                changes["tags"] = list(current | tag_ids)
            if changes:
                change_document(actor, document_id, changes)
        else:
            current = set(Document.objects.get(pk=document_id).tags.values_list("pk", flat=True))
            updated = current | tag_ids if action == "add_tags" else current - tag_ids
            if updated != current:
                change_document(actor, document_id, {"tags": list(updated)})
    return len(ids)


def lock_storage(sha256):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
        # Serialize duplicate checks with other writes of identical bytes.
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int.from_bytes(bytes.fromhex(sha256[:16]), "big", signed=True)])


def publish_version(document, actor, temporary, sha256, size, number, filename, note, source, restored_from=None):
    with temporary.open("rb") as stream:
        search_text = search.extract(stream, document.format)
    version_id = uuid.uuid4()
    path = storage.publish(temporary, document.id, version_id)
    version = Version.objects.create(
        id=version_id, document=document, number=number, path=path, filename=filename,
        sha256=sha256, size=size, note=note, created_by=actor, source=source,
        restored_from=restored_from, restored_from_number=restored_from.number if restored_from else None,
        search_text=search_text,
    )
    document.current_version = version
    document.save(update_fields=["current_version", "updated_at"])
    if document.format == Document.Format.MARKDOWN:
        from . import images, videos

        text = temporary.read_text(encoding="utf-8")
        images.record_references(version, text)
        videos.record_references(version, text)
        from .links import record_links

        record_links(version, text)
    activity.record_version(version)
    return version


def restore_version(actor, document_id, version_id, *, base_version, note=""):
    require_editor(actor)
    selected = get_object_or_404(Version.objects.defer("search_text"), pk=version_id, document_id=document_id, document__is_trashed=False)
    with storage.open_version(selected, document_id) as original, storage.stage(
        File(original), max_bytes=selected.size,
    ) as (temporary, sha256, size), transaction.atomic():
        if sha256 != selected.sha256 or size != selected.size:
            raise ValidationError({"detail": "舊版檔案完整性檢查失敗。"})
        lock_storage(sha256)
        document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
        previous = Version.objects.defer("search_text").get(pk=document.current_version_id)
        if previous.pk != base_version:
            raise VersionConflict()
        if previous.pk == selected.pk:
            raise ValidationError({"detail": "選擇一個舊版才能還原。"})
        version = publish_version(
            document, actor, temporary, sha256, size, previous.number + 1,
            selected.filename, note, "restore", restored_from=selected,
        )
        VersionRestoreAudit.objects.create(
            document=document, actor=actor, restored_from=selected, previous_version=previous, new_version=version,
            restored_from_number=selected.number, previous_number=previous.number, new_number=version.number,
        )
    return document


def delete_version(actor, document_id, version_id, *, number, reason=""):
    """Permanently delete one version (Admin only). The current and the published version cannot be deleted.

    Numbers are never reused or renumbered; the history shows where the version was.
    """
    if not has_role(actor, User.Role.ADMIN):
        raise PermissionDenied("只有 Admin 可以刪除版本。")
    with transaction.atomic():
        with connection.cursor() as cursor:
            # Shared like every other write, so a storage check never sees a half-deleted version.
            cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
        document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
        version = get_object_or_404(Version.objects.defer("search_text"), pk=version_id, document=document)
        if version.number != number:
            raise ValidationError({"number": f"版本號不符，請輸入 v{version.number} 確認。"})
        if version.pk == document.current_version_id:
            raise ValidationError({"detail": "目前版本不能刪除。請先用其他版本還原，再刪除這個版本。"})
        if ArticlePublication.objects.filter(document=document, version=version).exists():
            raise ValidationError({"detail": "公開中的版本不能刪除。請先改發布其他版本或下架。"})
        path = storage.root() / f"versions/{document.pk}/{version.pk}"
        if version.path != str(path.relative_to(storage.root())):
            raise ValidationError({"detail": "版本檔案位置不正確，請聯絡管理員檢查。"})
        version.delete()
        activity.record(document.pk, actor, activity.Action.VERSION_DELETED, version_number=number, reason=reason.strip())
        transaction.on_commit(lambda: remove_version_file(path))
    return document


def remove_version_file(path):
    try:
        path.unlink(missing_ok=True)
        storage.sync_directory(path.parent)
    except OSError:
        # Reported by check_document_storage as an unreferenced file; nothing refers to it any more.
        logger.error("Could not remove the file of a deleted version.")


def record_trash_action(document, actor, action):
    DocumentTrashAudit.objects.create(
        document_id=document.pk, title=document.title, actor=actor,
        action=action, version_count=document.versions.count(),
    )


MERGE_LIMIT = 50


def require_admin(user):
    if not has_role(user, User.Role.ADMIN):
        raise PermissionDenied("只有 Admin 可以合併標籤。")


@transaction.atomic
def merge_tags(actor, source_ids, target_id):
    """Move every document from the source tags onto the target tag, then delete the sources.

    Runs in one transaction with the tags and affected documents locked in a stable order.
    Each changed document gets a metadata activity entry; `updated_at` is left alone because
    tidying the taxonomy is not an edit of the document.
    """
    require_admin(actor)
    sources = list(dict.fromkeys(source_ids))
    if not sources or len(sources) > MERGE_LIMIT:
        raise ValidationError({"sources": f"請選擇 1 至 {MERGE_LIMIT} 個要合併的標籤。"})
    if target_id in sources:
        raise ValidationError({"target": "目標標籤不能同時是被合併的標籤。"})
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["knowledge-hub:tags"])
    tags = {tag.pk: tag for tag in Tag.objects.select_for_update().filter(pk__in=[*sources, target_id]).order_by("pk")}
    if target_id not in tags or any(pk not in tags for pk in sources):
        raise ValidationError({"detail": "部分標籤已不存在，請重新整理後再試。"})
    target = tags[target_id]
    # FOR UPDATE cannot be combined with DISTINCT: collect the ids, then lock those rows.
    affected = set(Document.tags.through.objects.filter(tag_id__in=sources).values_list("document_id", flat=True))
    documents = list(
        Document.objects.select_for_update(of=("self",)).filter(pk__in=affected).order_by("pk").select_related("category")
    )
    for document in documents:
        before = activity.metadata_snapshot(document)
        document.tags.remove(*sources)
        document.tags.add(target)
        activity.record_metadata(document, actor, before)
    Tag.objects.filter(pk__in=sources).delete()
    return {"target": str(target.pk), "merged": len(sources), "documents": len(documents)}

