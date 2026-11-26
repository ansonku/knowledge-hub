"""Document activity feed: one row per meaningful change, written inside the caller's transaction."""
from django.utils import timezone

from .models import DocumentActivity

Action = DocumentActivity.Action

VERSION_ACTIONS = {"markdown_edit": Action.EDITED, "restore": Action.RESTORED_VERSION}


def record(document_id, actor, action, *, version_number=None, **detail):
    DocumentActivity.objects.create(
        document_id=document_id, actor=actor if actor and actor.is_authenticated else None,
        action=action, version_number=version_number,
        detail={key: value for key, value in detail.items() if value not in (None, "", [], {})},
        created_at=timezone.now(),
    )


def record_version(version):
    if version.number == 1:
        action = Action.CREATED
    else:
        action = VERSION_ACTIONS.get(version.source, Action.UPLOADED)
    record(
        version.document_id, version.created_by, action, version_number=version.number,
        note=version.note, restored_from=version.restored_from_number,
    )


def record_metadata(document, actor, before):
    """Record title, collection, tag and presentation changes compared with the `before` snapshot."""
    changes = {}
    if before["title"] != document.title:
        changes["title"] = {"from": before["title"], "to": document.title}
    if before["category_id"] != document.category_id:
        changes["category"] = {
            "from": before["category_name"],
            "to": document.category.name if document.category_id else None,
        }
    for field in ("presentation", "gallery_layout"):
        if before[field] != getattr(document, field):
            changes[field] = {"from": before[field], "to": getattr(document, field)}
    if before["cover_image"] != document.cover_image_id:
        # P22: which picture is not meaningful in the feed; whether a cover was set, changed or removed is.
        changes["cover"] = {"from": bool(before["cover_image"]), "to": bool(document.cover_image_id)}
    tags = {tag.pk: tag.name for tag in document.tags.all()}
    added = sorted(name for pk, name in tags.items() if pk not in before["tags"])
    removed = sorted(name for pk, name in before["tags"].items() if pk not in tags)
    if added or removed:
        changes["tags"] = {"added": added, "removed": removed}
    if changes:
        record(document.pk, actor, Action.METADATA, **changes)


def metadata_snapshot(document):
    return {
        "title": document.title,
        "category_id": document.category_id,
        "category_name": document.category.name if document.category_id else None,
        "tags": {tag.pk: tag.name for tag in document.tags.all()},
        "presentation": document.presentation,
        "gallery_layout": document.gallery_layout,
        "cover_image": document.cover_image_id,
    }
