import uuid
from pathlib import Path

from django.core.files import File
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from users.models import User
from users.permissions import has_role

from . import storage
from .models import Document, Version, VersionRestoreAudit


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
            current = document.current_version
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


@transaction.atomic
def change_document(actor, document_id, data=None):
    require_editor(actor)
    document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
    if data is None:
        document.is_trashed = True
        document.save(update_fields=["is_trashed", "updated_at"])
    else:
        fields = [field for field in ("title", "category") if field in data]
        for field in fields:
            setattr(document, field, data[field])
        if "tags" in data:
            document.tags.set(data["tags"])
        document.save(update_fields=[*fields, "updated_at"])
    return document


def lock_storage(sha256):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
        # Serialize duplicate checks with other writes of identical bytes.
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int.from_bytes(bytes.fromhex(sha256[:16]), "big", signed=True)])


def publish_version(document, actor, temporary, sha256, size, number, filename, note, source, restored_from=None):
    version_id = uuid.uuid4()
    path = storage.publish(temporary, document.id, version_id)
    version = Version.objects.create(
        id=version_id, document=document, number=number, path=path, filename=filename,
        sha256=sha256, size=size, note=note, created_by=actor, source=source,
        restored_from=restored_from,
    )
    document.current_version = version
    document.save(update_fields=["current_version", "updated_at"])
    return version


def restore_version(actor, document_id, version_id, *, base_version, note=""):
    require_editor(actor)
    selected = get_object_or_404(Version, pk=version_id, document_id=document_id, document__is_trashed=False)
    with storage.open_version(selected, document_id) as original, storage.stage(
        File(original), max_bytes=selected.size,
    ) as (temporary, sha256, size), transaction.atomic():
        if sha256 != selected.sha256 or size != selected.size:
            raise ValidationError({"detail": "舊版檔案完整性檢查失敗。"})
        lock_storage(sha256)
        document = get_object_or_404(active_documents().select_for_update(), pk=document_id)
        previous = document.current_version
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
        )
    return document
