import uuid
from pathlib import Path

from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from users.models import User
from users.permissions import has_role

from . import storage
from .models import Document, Version


STORAGE_LOCK_KEY = "knowledge-hub:document-files"


class DuplicateContent(APIException):
    status_code = 409
    default_detail = "內容重複，請確認是否仍要儲存。"
    default_code = "duplicate_content"


def require_editor(actor):
    if not has_role(actor, User.Role.ADMIN, User.Role.EDITOR):
        raise PermissionDenied()


def active_documents():
    return Document.objects.filter(is_trashed=False)


def add_upload(actor, data, document_id=None):
    require_editor(actor)
    upload = data["file"]
    suffix = Path(upload.name).suffix.lower().removeprefix(".")
    if suffix not in Document.Format.values:
        raise ValidationError({"file": "只接受 .html 或 .md 檔案。"})
    with storage.stage(upload) as (temporary, sha256, size), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
            # Serialize duplicate checks with other writes of identical bytes.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int.from_bytes(bytes.fromhex(sha256[:16]), "big", signed=True)])
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
            if current.sha256 == sha256 and not data["force"]:
                raise DuplicateContent()
            number = current.number + 1

        version_id = uuid.uuid4()
        path = storage.publish(temporary, document.id, version_id)
        version = Version.objects.create(
            id=version_id, document=document, number=number, path=path, filename=upload.name,
            sha256=sha256, size=size, note=data.get("note", ""), created_by=actor,
        )
        document.current_version = version
        document.save(update_fields=["current_version", "updated_at"])
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
