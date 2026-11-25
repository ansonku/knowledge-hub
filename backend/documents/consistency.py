"""Compare the files on disk with the database: committed version files, pasted images and embedded videos."""
from django.db import connection, transaction

from .models import DocumentImage, DocumentVideo, PendingDocumentDeletion, Version
from .services import STORAGE_LOCK_KEY
from .storage import root, sync_directory


class QuarantineConflict(Exception):
    pass


@transaction.atomic
def inspect_storage(*, quarantine=False):
    """Returns (checked, missing, unreferenced) as sorted relative paths.

    Holds the storage lock exclusively, so no version or image is written meanwhile.
    With quarantine=True, unreferenced files move to quarantine/ (nothing is deleted).
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
    base = root()
    expected = set(Version.objects.values_list("path", flat=True))
    expected |= {image.path for image in DocumentImage.objects.only("pk", "document_id", "format")}
    expected |= {video.path for video in DocumentVideo.objects.only("pk", "document_id", "format")}
    pending = {str(item) for item in PendingDocumentDeletion.objects.values_list("pk", flat=True)}
    present = {
        str(path.relative_to(base)) for folder in ("versions", "images", "videos")
        for path in (base / folder).glob("*/*")
        # .upload-* are videos still arriving; they never get a row of their own.
        if path.is_file() and path.parent.name not in pending and not path.name.startswith(".upload-")
    }
    unreferenced = sorted(present - expected)
    if quarantine:
        for path in unreferenced:
            source = base / path
            destination = base / "quarantine" / path
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if destination.exists():
                raise QuarantineConflict(path)
            source.rename(destination)
            sync_directory(source.parent)
            sync_directory(destination.parent)
    return len(expected), sorted(expected - present), unreferenced
