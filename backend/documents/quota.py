"""P23: an overall storage limit inside the system (not the host's quota: it may not run on a NAS).

Usage is summed from recorded sizes (no walking the storage tree): the database, every version
(old and trashed ones too), images and videos. Thumbnails, backups, logs and temporary files are
not counted; the free-disk check below covers them."""
import logging
import shutil

from django.db.models import F, Sum
from django.conf import settings
from django.db import transaction
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from users.lifecycle import audit
from users.permissions import IsAdmin

from . import storage
from .models import DocumentImage, DocumentVideo, SiteSettings, Version, VersionImage, VersionVideo

logger = logging.getLogger(__name__)

GB = 1024 ** 3
MIN_LIMIT = GB
NOTICE_SHARE, WARNING_SHARE = 0.8, 0.9


class StorageFull(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "storage_full"


def size_label(size):
    return f"{size / GB:.1f} GB" if size >= GB / 10 else f"{max(1, round(size / 1024 / 1024))} MB"


def database_bytes():
    from hub.system import database_size  # hub.system imports documents; import lazily
    return database_size() or 0


def media_breakdown(model, through, field):
    """Bytes of a document's images or videos: used by the current version, by old versions only, or by none; trashed apart."""
    live = model.objects.filter(document__is_trashed=False)
    current_ids = through.objects.filter(version_id=F("version__document__current_version_id")).values(field)
    any_ids = through.objects.values(field)
    total = lambda rows: rows.aggregate(total=Sum("size"))["total"] or 0  # noqa: E731
    return {
        "current": total(live.filter(pk__in=current_ids)),
        "old": total(live.filter(pk__in=any_ids).exclude(pk__in=current_ids)),
        "unused": total(live.exclude(pk__in=any_ids)),
        "trash": total(model.objects.filter(document__is_trashed=True)),
    }


def usage():
    """{"total", "parts": {...}}: what the limit is measured against."""
    versions = Version.objects.values("size")
    current = versions.filter(pk=F("document__current_version_id"), document__is_trashed=False).aggregate(s=Sum("size"))["s"] or 0
    old = versions.filter(document__is_trashed=False).exclude(pk=F("document__current_version_id")).aggregate(s=Sum("size"))["s"] or 0
    trashed = versions.filter(document__is_trashed=True).aggregate(s=Sum("size"))["s"] or 0
    images = media_breakdown(DocumentImage, VersionImage, "image")
    videos = media_breakdown(DocumentVideo, VersionVideo, "video")
    parts = {
        "database": database_bytes(),
        "versions_current": current,
        "versions_old": old,
        "images": images["current"] + images["old"] + images["unused"],
        "videos": videos["current"] + videos["old"] + videos["unused"],
        "trash": trashed + images["trash"] + videos["trash"],
    }
    return {"total": sum(parts.values()), "parts": parts, "images": images, "videos": videos}


def disk():
    try:
        found = shutil.disk_usage(storage.root())
    except OSError:
        return None
    return {"total_bytes": found.total, "free_bytes": found.free}


def level(used, limit):
    """None, "notice" (80 %), "warning" (90 %) or "full" (100 %)."""
    if not limit:
        return None
    share = used / limit
    return "full" if share >= 1 else "warning" if share >= WARNING_SHARE else "notice" if share >= NOTICE_SHARE else None


def check_space(incoming):
    """Refuse an upload of `incoming` bytes that would pass the limit or leave the disk nearly full. Raises StorageFull."""
    found = disk()
    if found and found["free_bytes"] - incoming < settings.UPLOAD_MIN_FREE_BYTES:
        logger.error("Upload refused: less than %d bytes of disk space would remain.", settings.UPLOAD_MIN_FREE_BYTES)
        raise StorageFull({"file": "伺服器磁碟空間不足，暫時無法上傳。請通知管理員清理空間。", "reason": "disk"})
    limit = SiteSettings.current().storage_limit
    if not limit:
        return
    used = usage()["total"]
    if used + incoming > limit:
        logger.warning("Upload refused: storage limit %d reached (used %d, incoming %d).", limit, used, incoming)
        raise StorageFull({
            "file": f"儲存空間已達上限（已用 {size_label(used)}／上限 {size_label(limit)}），請聯絡管理員。",
            "reason": "limit", "used": used, "limit": limit,
        })


class LimitInput(serializers.Serializer):
    limit = serializers.IntegerField(min_value=MIN_LIMIT, allow_null=True)


def report():
    limit = SiteSettings.current().storage_limit
    used = usage()
    return {
        "limit": limit, "used": used["total"], "parts": used["parts"], "images": used["images"], "videos": used["videos"],
        "share": used["total"] / limit if limit else None, "level": level(used["total"], limit), "disk": disk(),
        "min_free_bytes": settings.UPLOAD_MIN_FREE_BYTES,
    }


@never_cache
@api_view(["GET", "PUT"])
@permission_classes([IsAdmin])
def storage_settings(request):
    """P23: the storage limit and what counts towards it (Admins)."""
    if request.method == "PUT":
        payload = LimitInput(data=request.data)
        payload.is_valid(raise_exception=True)
        value = payload.validated_data["limit"]
        with transaction.atomic():
            site, _ = SiteSettings.objects.select_for_update().get_or_create(pk=1)
            if site.storage_limit != value:
                audit("storage_limit_updated", request.user, actor=request.user, limit={"from": site.storage_limit, "to": value})
                site.storage_limit = value
                site.updated_by = request.user
                site.save()
    return Response(report())
