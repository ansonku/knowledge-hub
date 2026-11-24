"""Images pasted into Markdown documents.

Every image belongs to one document and is readable exactly when that document is:
members can read images of documents that are not in the trash, and visitors can read
the images that the document's published version refers to. Uploads are decoded and
re-encoded with Pillow, which drops EXIF (GPS position and the like) and anything that
is not image data. SVG is never accepted because it can carry scripts.
"""
import hashlib
import io
import logging
import os
import re
import tempfile
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, OuterRef
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from users.models import User
from users.permissions import CanReadLibrary, has_role

from . import services, storage
from .models import ArticlePublication, Document, DocumentImage, VersionImage

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
# An image no version refers to is kept this long after its last upload, then removed.
GRACE = timedelta(hours=24)
MAX_PIXELS = 40_000_000
MAX_FRAMES = 500

# Magic numbers decide the format; the file name and the browser's declared type are ignored.
SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png", "PNG"),
    (b"\xff\xd8\xff", "jpeg", "JPEG"),
    (b"GIF87a", "gif", "GIF"),
    (b"GIF89a", "gif", "GIF"),
)
CONTENT_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
# Image links as the editor writes them, relative or absolute: /api/images/<uuid>/
REFERENCE = re.compile(r"/api/images/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/")


class ImageUploadThrottle(UserRateThrottle):
    scope = "image_upload"
    rate = "120/hour"


def sniff(head):
    for signature, name, pillow in SIGNATURES:
        if head.startswith(signature):
            return name, pillow
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "WEBP"
    raise ValidationError({"file": "只接受 PNG、JPEG、GIF 或 WebP 圖片。"})


def read_limited(upload):
    data = bytearray()
    for chunk in upload.chunks():
        data += chunk
        if len(data) > MAX_BYTES:
            raise ValidationError({"file": "圖片超過 10 MB。"})
    if not data:
        raise ValidationError({"file": "檔案不得為空。"})
    return bytes(data)


def reencode(data):
    """Decode and re-encode the image. Returns (bytes, format, width, height)."""
    name, pillow = sniff(data[:16])
    try:
        with Image.open(io.BytesIO(data), formats=[pillow]) as source:
            width, height = source.size
            frames = getattr(source, "n_frames", 1)
            if width * height > MAX_PIXELS or frames > MAX_FRAMES or width * height * frames > MAX_PIXELS * 4:
                raise ValidationError({"file": "圖片尺寸過大（上限 4000 萬像素）。"})
            output = io.BytesIO()
            if frames > 1 and name in ("gif", "webp"):
                save_animation(source, output, pillow)
            else:
                save_still(ImageOps.exif_transpose(source), output, name, pillow, source.info.get("icc_profile"))
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError({"file": "圖片無法讀取，可能已損壞。"}) from None
    encoded = output.getvalue()
    with Image.open(io.BytesIO(encoded)) as check:
        width, height = check.size
    return encoded, name, width, height


def save_still(image, output, name, pillow, icc_profile):
    image.load()
    options = {"icc_profile": icc_profile} if icc_profile else {}
    if name == "jpeg":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(output, pillow, quality=90, optimize=True, **options)
    elif name == "gif":
        image.save(output, pillow)
    elif name == "webp":
        image.save(output, pillow, quality=90, **options)
    else:
        image.save(output, pillow, optimize=True, **options)


def save_animation(source, output, pillow):
    frames, durations = [], []
    for index in range(source.n_frames):
        source.seek(index)
        frames.append(source.convert("RGBA"))
        durations.append(source.info.get("duration", 100))
    frames[0].save(
        output, pillow, save_all=True, append_images=frames[1:], duration=durations,
        loop=source.info.get("loop", 0), disposal=2,
    )


def write_file(image, encoded):
    images = storage.root() / "images"
    images.mkdir(mode=0o700, exist_ok=True)
    folder = images / str(image.document_id)
    folder.mkdir(mode=0o700, exist_ok=True)
    destination = storage.root() / image.path
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
    os.replace(temporary.name, destination)
    storage.sync_directory(folder)


def add_image(actor, document_id, upload):
    services.require_editor(actor)
    document = get_object_or_404(services.active_documents(), pk=document_id)
    if document.format != Document.Format.MARKDOWN:
        raise ValidationError({"file": "只有 Markdown 文件可以插入圖片。"})
    encoded, name, width, height = reencode(read_limited(upload))
    digest = hashlib.sha256(encoded).hexdigest()
    with transaction.atomic():
        # Shared with version saves; the cleanup takes it exclusively, so it never removes an image being reused.
        lock_storage(shared=True)
        existing = DocumentImage.objects.filter(document=document, sha256=digest).first()
        if existing:
            # Pasting it again restarts the grace period.
            DocumentImage.objects.filter(pk=existing.pk).update(uploaded_at=timezone.now())
            return existing, False
        image = DocumentImage(
            document=document, sha256=digest, format=name, width=width, height=height, size=len(encoded), created_by=actor,
        )
        # The file is in place before the row exists, so a row never points at a missing file.
        write_file(image, encoded)
        try:
            with transaction.atomic():
                image.save(force_insert=True)
        except IntegrityError:
            (storage.root() / image.path).unlink(missing_ok=True)
            return DocumentImage.objects.get(document=document, sha256=digest), False
    return image, True


def lock_storage(*, shared):
    with connection.cursor() as cursor:
        function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        cursor.execute(f"SELECT {function}(hashtext(%s), 0)", [services.STORAGE_LOCK_KEY])


def unused_images(now=None):
    """Images that no version refers to and that were last uploaded more than the grace period ago."""
    referenced = VersionImage.objects.filter(image=OuterRef("pk"))
    return DocumentImage.objects.filter(uploaded_at__lt=(now or timezone.now()) - GRACE).exclude(Exists(referenced))


def collect_unused_images(*, dry_run=False):
    """Remove unused images past the grace period. Returns (count, bytes)."""
    with transaction.atomic():
        lock_storage(shared=False)
        victims = list(unused_images().values_list("pk", "document_id", "format", "size"))
        if dry_run or not victims:
            return len(victims), sum(row[3] for row in victims)
        DocumentImage.objects.filter(pk__in=[row[0] for row in victims]).delete()
        paths = [storage.root() / "images" / str(document) / f"{pk}.{fmt}" for pk, document, fmt, _ in victims]
        transaction.on_commit(lambda: remove_files(paths))
    total = sum(row[3] for row in victims)
    logger.info("Removed %d unused images (%d bytes).", len(victims), total)
    return len(victims), total


def remove_files(paths):
    folders = set()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            folders.add(path.parent)
        except OSError:
            # check_document_storage reports the leftover file; nothing refers to it any more.
            logger.error("Could not remove an unused image file.")
    for folder in folders:
        try:
            storage.sync_directory(folder)
            folder.rmdir()
        except OSError:
            pass  # Not empty: other images of the document remain.


def collect_occasionally():
    """Run the cleanup at most once an hour, piggybacking on uploads (which are what leave unused images)."""
    if not cache.add("documents:collect-unused-images", 1, 3600):
        return
    try:
        collect_unused_images()
    except Exception:
        logger.exception("Unused image cleanup failed.")


def record_references(version, text):
    """Remember which of its own document's images a version refers to. Other documents' images never count."""
    ids = set(REFERENCE.findall(text))
    if not ids:
        return
    images = DocumentImage.objects.filter(document_id=version.document_id, pk__in=ids).values_list("pk", flat=True)
    VersionImage.objects.bulk_create([VersionImage(version=version, image_id=pk) for pk in images], ignore_conflicts=True)


def image_payload(image):
    return {
        "id": str(image.pk), "url": f"/api/images/{image.pk}/", "format": image.format,
        "width": image.width, "height": image.height, "size": image.size,
    }


@api_view(["POST"])
@permission_classes([CanReadLibrary])
@throttle_classes([ImageUploadThrottle])
def upload_image(request, document_id):
    upload = request.FILES.get("file")
    if upload is None:
        raise ValidationError({"file": "請選擇圖片。"})
    image, created = add_image(request.user, document_id, upload)
    collect_occasionally()
    return Response(image_payload(image), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


def can_read(user, image):
    document = image.document
    if document.is_trashed:
        return False
    if has_role(user, *User.Role.values):
        return True
    publication = ArticlePublication.objects.filter(document_id=document.pk).only("version_id").first()
    return bool(publication) and VersionImage.objects.filter(version_id=publication.version_id, image=image).exists()


@api_view(["GET"])
@permission_classes([AllowAny])
def serve_image(request, image_id):
    image = DocumentImage.objects.select_related("document").filter(pk=image_id).first()
    # Missing and forbidden look the same, so the response never tells whether an image exists.
    if image is None or not can_read(request.user, image):
        raise Http404
    try:
        handle = (storage.root() / image.path).open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(handle, content_type=CONTENT_TYPES[image.format])
    response["Content-Disposition"] = f'inline; filename="image.{image.format}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    # Bytes behind an id never change; access can, so keep it to the browser and only briefly.
    response["Cache-Control"] = "private, max-age=600"
    response["Vary"] = "Cookie"
    return response
