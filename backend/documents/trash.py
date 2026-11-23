import logging
import shutil

from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from users.models import User
from users.permissions import has_role

from . import storage
from .models import Document, PendingDocumentDeletion, Version
from .services import STORAGE_LOCK_KEY, record_trash_action, require_editor

logger = logging.getLogger(__name__)


@transaction.atomic
def restore_document(actor, document_id):
    require_editor(actor)
    document = get_object_or_404(Document.objects.select_for_update(), pk=document_id, is_trashed=True)
    document.is_trashed = False
    document.trashed_at = None
    document.save(update_fields=["is_trashed", "trashed_at", "updated_at"])
    record_trash_action(document, actor, "restored")
    return document


@transaction.atomic
def queue_permanent_deletion(actor, document_id, *, confirm, title):
    if not has_role(actor, User.Role.ADMIN):
        raise PermissionDenied()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
    document = get_object_or_404(Document.objects.select_for_update(), pk=document_id, is_trashed=True)
    if not confirm or title != document.title:
        raise ValidationError({"detail": "請確認永久刪除並輸入完整文件標題。"})
    record_trash_action(document, actor, "permanent")
    PendingDocumentDeletion.objects.create(document_id=document_id)
    # Remove references between rows that are all going away in this transaction.
    document.current_version = None
    document.save(update_fields=["current_version"])
    Version.objects.filter(document=document).update(restored_from=None)
    document.delete()


@transaction.atomic
def finish_permanent_deletion(document_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
    job = PendingDocumentDeletion.objects.select_for_update().filter(pk=document_id).first()
    if job is None:
        return True
    base = storage.root()
    versions = base / "versions"
    try:
        if not versions.is_dir():
            raise OSError("Version storage is unavailable.")
        for directory in (versions, base / "quarantine" / "versions"):
            victim = directory / str(job.document_id)
            if victim.exists():
                shutil.rmtree(victim)
            if directory.exists():
                storage.sync_directory(directory)
    except OSError:
        logger.error("Permanent document file deletion is pending for %s", document_id)
        return False
    job.delete()
    return True
