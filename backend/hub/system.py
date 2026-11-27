"""Admin system status: counts, storage, background work and configuration flags.

Read-only and cheap: aggregate queries plus one disk_usage() call; it never walks the
storage tree (`check_document_storage` does that on demand). Responses carry numbers and
booleans only: no file paths, host names, environment values or secrets.
"""
import shutil

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.db import DatabaseError, connection
from django.db.models import Count, F, Min, Q, Sum
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from documents import limits
from documents.images import unused_images
from documents.videos import unused_videos
from documents.models import (
    ArticlePublication, Category, Document, DocumentImage, DocumentVideo, PendingDocumentDeletion, SiteSettings, Tag, Version,
)
from users.models import User
from users.permissions import IsAdmin

from .maintenance import last_run

LOW_DISK_SHARE = 0.10


def database_size():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            return cursor.fetchone()[0]
    except DatabaseError:
        return None


def disk():
    try:
        usage = shutil.disk_usage(settings.DOCUMENT_STORAGE)
    except OSError:
        return None
    return {"total_bytes": usage.total, "free_bytes": usage.free}


def limit_status():
    """P23: the storage limit, what counts towards it, and how close it is."""
    from documents import quota
    limit = SiteSettings.current().storage_limit
    used = quota.usage()["total"]
    return {"limit_bytes": limit, "counted_bytes": used, "limit_level": quota.level(used, limit)}


STORAGE_NOTES = {
    "notice": ("warning", "儲存空間已用超過 80%。"),
    "warning": ("danger", "儲存空間已用超過 90%，接近上限。"),
    "full": ("danger", "儲存空間已達上限，新的上傳會被拒絕。"),
}


def warnings(report):
    notes = []
    jobs, config, members, storage = report["jobs"], report["config"], report["members"], report["storage"]
    if jobs["pending_deletions"]:
        notes.append({"level": "warning", "key": "pending_deletions",
                      "text": f"有 {jobs['pending_deletions']} 個永久刪除的檔案清理還沒完成。重新啟動服務時會自動重試，"
                              "也可以按「背景工作」的「立即執行維護」。"})
    if jobs["unindexed_documents"]:
        notes.append({"level": "warning", "key": "unindexed",
                      "text": f"有 {jobs['unindexed_documents']} 份文件的目前版本還沒有搜尋索引，搜尋時可能找不到內文。"
                              "可以按「背景工作」的「立即執行維護」補建。"})
    checked = (report["maintenance"] or {}).get("results", {}).get("storage", {})
    if checked.get("missing"):
        notes.append({"level": "danger", "key": "missing_files",
                      "text": f"上次維護檢查發現 {checked['missing']} 個文件或圖片檔案遺失，請從備份還原，"
                              "並在主機上執行 `check_document_storage` 查看是哪些檔案。"})
    if storage["disk"] and storage["disk"]["free_bytes"] < storage["disk"]["total_bytes"] * LOW_DISK_SHARE:
        notes.append({"level": "danger", "key": "low_disk", "text": "文件儲存空間所在的磁碟剩餘不到 10%。"})
    if storage.get("limit_level"):
        tone, text = STORAGE_NOTES[storage["limit_level"]]
        notes.append({"level": tone, "key": "storage_limit",
                      "text": f"{text}可以在「儲存空間」查看各類檔案的用量，清空回收桶或刪除不需要的舊版本與影片。"})
    if members["active_admins"] < 2:
        notes.append({"level": "info", "key": "single_admin",
                      "text": "目前只有一位使用中的 Admin。停用帳號、重設雙因素驗證等操作需要另一位 Admin 才能對這位 Admin 執行。"})
    if not config["smtp"]:
        notes.append({"level": "info", "key": "smtp",
                      "text": "尚未設定 SMTP：邀請、密碼重設與通知信只會寫入伺服器的檔案，不會寄出。"})
    if config["https"] and not config["mfa_key"]:
        notes.append({"level": "danger", "key": "mfa_key",
                      "text": "已使用 HTTPS 對外，但沒有設定 MFA_ENCRYPTION_KEY，雙因素驗證金鑰目前由 Django 密鑰衍生。"})
    return notes


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def system_status(request):
    documents = Document.objects.aggregate(
        active=Count("pk", filter=Q(is_trashed=False)), trashed=Count("pk", filter=Q(is_trashed=True)),
    )
    versions = Version.objects.aggregate(count=Count("pk"), bytes=Sum("size"))
    images = DocumentImage.objects.aggregate(count=Count("pk"), bytes=Sum("size"))
    unused = unused_images().aggregate(count=Count("pk"), bytes=Sum("size"))
    videos = DocumentVideo.objects.aggregate(count=Count("pk"), bytes=Sum("size"))
    unused_video = unused_videos().aggregate(count=Count("pk"), bytes=Sum("size"))
    pending = PendingDocumentDeletion.objects.aggregate(count=Count("pk"), oldest=Min("created_at"))
    people = User.objects.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=Q(is_active=True, pending_activation=False)),
        pending=Count("pk", filter=Q(pending_activation=True)),
        disabled=Count("pk", filter=Q(is_active=False, pending_activation=False)),
        admins=Count("pk", filter=Q(role=User.Role.ADMIN)),
        editors=Count("pk", filter=Q(role=User.Role.EDITOR)),
        viewers=Count("pk", filter=Q(role=User.Role.VIEWER)),
        active_admins=Count("pk", filter=Q(role=User.Role.ADMIN, is_active=True, pending_activation=False)),
    )
    report = {
        "generated_at": timezone.now(),
        "content": {
            "documents": documents["active"], "trashed": documents["trashed"], "versions": versions["count"],
            "published": ArticlePublication.objects.filter(document__is_trashed=False).count(),
            "collections": Category.objects.count(), "tags": Tag.objects.count(), "images": images["count"],
            "videos": videos["count"],
        },
        "storage": {
            "versions_bytes": versions["bytes"] or 0, "images_bytes": images["bytes"] or 0,
            "videos_bytes": videos["bytes"] or 0,
            "database_bytes": database_size(), "disk": disk(),
            **limit_status(),
        },
        "members": {
            "total": people["total"], "active": people["active"], "pending": people["pending"], "disabled": people["disabled"],
            "by_role": {"admin": people["admins"], "editor": people["editors"], "viewer": people["viewers"]},
            "active_admins": people["active_admins"],
            "mfa_enabled": Authenticator.objects.values("user").distinct().count(),
        },
        "jobs": {
            "pending_deletions": pending["count"], "oldest_pending_deletion": pending["oldest"],
            # Normally near zero: the cleanup runs at start-up and at most hourly after uploads.
            "unused_images": unused["count"], "unused_images_bytes": unused["bytes"] or 0,
            "unused_videos": unused_video["count"], "unused_videos_bytes": unused_video["bytes"] or 0,
            "unindexed_documents": Version.objects.filter(
                search_text__isnull=True, pk=F("document__current_version_id"), document__is_trashed=False,
            ).count(),
        },
        "config": {
            "https": settings.PUBLIC_ORIGIN.startswith("https://"),
            "google_login": settings.GOOGLE_CONFIGURED,
            "smtp": bool(settings.EMAIL_HOST),
            "mfa_key": bool(settings.MFA_ENCRYPTION_KEY),
            "html_preview": settings.LOCAL_HTML_PREVIEW,
            "file_limits": limits.for_members(),
            "max_batch": settings.DOCUMENT_MAX_BATCH,
        },
    }
    report["maintenance"] = last_run()
    report["warnings"] = warnings(report)
    return Response(report)
