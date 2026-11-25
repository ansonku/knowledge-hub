"""Videos embedded in Markdown documents (P10).

They follow the image rules (documents/images.py): every video belongs to one document and is readable exactly
when that document is; visitors get only the videos that the document's published version refers to. Unlike
images, the bytes are stored as uploaded: only MP4 and WebM are accepted, decided by the file header, and the
codec is not checked (a video the browser cannot play shows a hint to convert it).

Django never streams video bytes. After checking access it answers with X-Accel-Redirect and nginx sends the
file from an internal location, which handles Range requests (seeking) without tying up a gunicorn worker.
nginx mounts only DOCUMENT_STORAGE/videos/, read-only; video folders and files are group-readable for that.
"""
import hashlib
import logging
import os
import re
import shutil
import tempfile

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from users.models import User
from users.permissions import CanReadLibrary, has_role

from . import services, storage
from .images import GRACE, collect_occasionally, lock_storage, remove_files
from .models import ArticlePublication, Document, DocumentVideo, VersionVideo

logger = logging.getLogger(__name__)

CONTENT_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
# Video links as the editor writes them, relative or absolute: /api/videos/<uuid>/
REFERENCE = re.compile(r"/api/videos/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/")
FOLDER_MODE = 0o750  # nginx reads through the shared group
FILE_MODE = 0o640
UNSUPPORTED = "只接受 MP4 或 WebM 影片。其他格式（例如 iPhone 的 .mov）請先轉成 MP4（H.264）。"


class VideoUploadThrottle(UserRateThrottle):
    scope = "video_upload"
    rate = "30/hour"


def sniff(head):
    """The format from the first bytes; the file name and the browser's declared type are ignored."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        # QuickTime (.mov) shares the box layout; its major brand is "qt  ".
        if head[8:12] == b"qt  ":
            raise ValidationError({"file": UNSUPPORTED})
        return "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        # EBML header: WebM declares DocType "webm"; other Matroska files say "matroska".
        if b"\x42\x82" in head[:64] and b"webm" in head[:64]:
            return "webm"
    raise ValidationError({"file": UNSUPPORTED})


def video_folder(document_id):
    base = storage.root() / "videos"
    for folder in (base, base / str(document_id)):
        folder.mkdir(exist_ok=True)
        os.chmod(folder, FOLDER_MODE)
    return base / str(document_id)


def check_free_space(size):
    try:
        free = shutil.disk_usage(storage.root()).free
    except OSError:
        return
    if free - size < settings.VIDEO_MIN_FREE_BYTES:
        logger.error("Video upload refused: less than %d bytes of disk space would remain.", settings.VIDEO_MIN_FREE_BYTES)
        raise ValidationError({"file": "伺服器磁碟空間不足，暫時無法上傳影片。請通知管理員清理空間。"})


def receive(upload, folder):
    """Copy the upload next to its final place while hashing it. Returns (temporary path, sha256, size)."""
    limit = settings.VIDEO_MAX_BYTES
    digest = hashlib.sha256()
    size = 0
    temporary = tempfile.NamedTemporaryFile(dir=folder, prefix=".upload-", delete=False)
    try:
        with temporary:
            for chunk in upload.chunks():
                size += len(chunk)
                if size > limit:
                    raise ValidationError({"file": f"影片超過 {limit // (1024 * 1024)} MB。"})
                digest.update(chunk)
                temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary.name, FILE_MODE)
    except BaseException:
        os.unlink(temporary.name)
        raise
    return temporary.name, digest.hexdigest(), size


def add_video(actor, document_id, upload):
    services.require_editor(actor)
    document = get_object_or_404(services.active_documents(), pk=document_id)
    if document.format != Document.Format.MARKDOWN:
        raise ValidationError({"file": "只有 Markdown 文件可以插入影片。"})
    if not upload.size:
        raise ValidationError({"file": "檔案不得為空。"})
    if upload.size > settings.VIDEO_MAX_BYTES:
        raise ValidationError({"file": f"影片超過 {settings.VIDEO_MAX_BYTES // (1024 * 1024)} MB。"})
    head = upload.read(64)
    upload.seek(0)
    name = sniff(head)
    check_free_space(upload.size)
    folder = video_folder(document.pk)
    temporary, digest, size = receive(upload, folder)
    try:
        with transaction.atomic():
            # Shared with version saves; the cleanup takes it exclusively, so it never removes a video being reused.
            lock_storage(shared=True)
            existing = DocumentVideo.objects.filter(document=document, sha256=digest).first()
            if existing:
                # Uploading it again restarts the grace period.
                DocumentVideo.objects.filter(pk=existing.pk).update(uploaded_at=timezone.now())
                return existing, False
            video = DocumentVideo(document=document, sha256=digest, format=name, size=size, created_by=actor)
            # The file is in place before the row exists, so a row never points at a missing file.
            os.replace(temporary, storage.root() / video.path)
            temporary = None
            storage.sync_directory(folder)
            try:
                with transaction.atomic():
                    video.save(force_insert=True)
            except IntegrityError:
                (storage.root() / video.path).unlink(missing_ok=True)
                return DocumentVideo.objects.get(document=document, sha256=digest), False
    finally:
        if temporary:
            os.unlink(temporary)
    return video, True


def unused_videos(now=None):
    """Videos that no version refers to and that were last uploaded more than the grace period ago."""
    referenced = VersionVideo.objects.filter(video=OuterRef("pk"))
    return DocumentVideo.objects.filter(uploaded_at__lt=(now or timezone.now()) - GRACE).exclude(Exists(referenced))


def remove_abandoned_uploads(now=None):
    """Partial uploads left by a crash (normal ones are renamed or removed right away)."""
    cutoff = (now or timezone.now()).timestamp() - GRACE.total_seconds()
    for path in (storage.root() / "videos").glob("*/.upload-*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            logger.error("Could not remove an abandoned video upload.")


def collect_unused_videos(*, dry_run=False):
    """Remove unused videos past the grace period. Returns (count, bytes)."""
    if not dry_run:
        remove_abandoned_uploads()
    with transaction.atomic():
        lock_storage(shared=False)
        victims = list(unused_videos().values_list("pk", "document_id", "format", "size"))
        if dry_run or not victims:
            return len(victims), sum(row[3] for row in victims)
        DocumentVideo.objects.filter(pk__in=[row[0] for row in victims]).delete()
        paths = [storage.root() / "videos" / str(document) / f"{pk}.{fmt}" for pk, document, fmt, _ in victims]
        transaction.on_commit(lambda: remove_files(paths))
    total = sum(row[3] for row in victims)
    logger.info("Removed %d unused videos (%d bytes).", len(victims), total)
    return len(victims), total


def record_references(version, text):
    """Remember which of its own document's videos a version refers to. Other documents' videos never count."""
    ids = set(REFERENCE.findall(text))
    if not ids:
        return
    videos = DocumentVideo.objects.filter(document_id=version.document_id, pk__in=ids).values_list("pk", flat=True)
    VersionVideo.objects.bulk_create([VersionVideo(version=version, video_id=pk) for pk in videos], ignore_conflicts=True)


def video_payload(video):
    return {"id": str(video.pk), "url": f"/api/videos/{video.pk}/", "format": video.format, "size": video.size}


@api_view(["POST"])
@permission_classes([CanReadLibrary])
@throttle_classes([VideoUploadThrottle])
def upload_video(request, document_id):
    upload = request.FILES.get("file")
    if upload is None:
        raise ValidationError({"file": "請選擇影片。"})
    video, created = add_video(request.user, document_id, upload)
    collect_occasionally()
    return Response(video_payload(video), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


def can_read(user, video):
    document = video.document
    if document.is_trashed:
        return False
    if has_role(user, *User.Role.values):
        return True
    publication = ArticlePublication.objects.filter(document_id=document.pk).only("version_id").first()
    return bool(publication) and VersionVideo.objects.filter(version_id=publication.version_id, video=video).exists()


@api_view(["GET"])
@permission_classes([AllowAny])
def serve_video(request, video_id):
    video = DocumentVideo.objects.select_related("document").filter(pk=video_id).first()
    # Missing and forbidden look the same, so the response never tells whether a video exists.
    if video is None or not can_read(request.user, video) or not (storage.root() / video.path).is_file():
        raise Http404
    response = HttpResponse(content_type=CONTENT_TYPES[video.format])
    # nginx sends the file (with Range support) from its internal location; nosniff and the sandbox CSP are set there.
    response["X-Accel-Redirect"] = f"{settings.VIDEO_ACCEL_PREFIX}{video.document_id}/{video.pk}.{video.format}"
    response["Content-Disposition"] = f'inline; filename="video.{video.format}"'
    response["X-Content-Type-Options"] = "nosniff"
    # Bytes behind an id never change; access can, so keep it to the browser and only briefly.
    response["Cache-Control"] = "private, max-age=600"
    response["Vary"] = "Cookie"
    return response
