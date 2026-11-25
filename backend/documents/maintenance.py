"""Maintenance steps that normally run at start-up; Admins can also run them from the system status page."""
import logging

from django.db.models import F
from django.http import Http404

from . import search, storage
from .images import collect_unused_images
from .videos import collect_unused_videos
from .consistency import inspect_storage
from .models import PendingDocumentDeletion, Version
from .trash import finish_permanent_deletion

logger = logging.getLogger(__name__)


def retry_deletions():
    """Remove the files of permanently deleted documents that an earlier attempt left behind."""
    done = failed = 0
    for document_id in PendingDocumentDeletion.objects.values_list("pk", flat=True).iterator():
        if finish_permanent_deletion(document_id):
            done += 1
        else:
            failed += 1
    return {"done": done, "failed": failed}


def index_missing():
    """Extract the search text of current versions that have none yet."""
    indexed = failed = 0
    pending = Version.objects.filter(
        search_text__isnull=True, pk=F("document__current_version_id"),
    ).select_related("document")
    for version in pending.iterator(chunk_size=25):
        try:
            with storage.open_version(version, version.document_id) as stream:
                text = search.extract(stream, version.document.format)
        except (Http404, OSError, UnicodeError):
            logger.warning("Could not index version %s.", version.pk)
            failed += 1
        else:
            indexed += Version.objects.filter(pk=version.pk, search_text__isnull=True).update(search_text=text)
    return {"indexed": indexed, "failed": failed}


def remove_unused_images():
    count, size = collect_unused_images()
    return {"removed": count, "bytes": size}


def remove_unused_videos():
    count, size = collect_unused_videos()
    return {"removed": count, "bytes": size}


def check_storage():
    """Read-only: counts only, never paths, so nothing about the server layout reaches the page."""
    checked, missing, unreferenced = inspect_storage()
    if missing:
        logger.error("Storage check: %d committed files are missing.", len(missing))
    return {"checked": checked, "missing": len(missing), "unreferenced": len(unreferenced)}


STEPS = (
    ("deletions", retry_deletions),
    ("index", index_missing),
    ("images", remove_unused_images),
    ("videos", remove_unused_videos),
    ("storage", check_storage),
)
