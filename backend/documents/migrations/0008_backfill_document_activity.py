from django.db import migrations

VERSION_ACTIONS = {"markdown_edit": "edited", "restore": "restored_version"}


def backfill(apps, schema_editor):
    """Seed the activity feed from existing versions, trash and publication audits.

    Metadata edits were never audited, so they only appear from this release on.
    Events of permanently deleted documents are skipped: their rows are gone.
    """
    Document = apps.get_model("documents", "Document")
    Version = apps.get_model("documents", "Version")
    DocumentTrashAudit = apps.get_model("documents", "DocumentTrashAudit")
    ArticlePublicationAudit = apps.get_model("documents", "ArticlePublicationAudit")
    DocumentActivity = apps.get_model("documents", "DocumentActivity")
    existing = set(Document.objects.values_list("pk", flat=True))
    rows = []

    versions = Version.objects.values(
        "document_id", "created_by_id", "number", "source", "note", "created_at", "restored_from__number",
    )
    for version in versions.iterator():
        action = "created" if version["number"] == 1 else VERSION_ACTIONS.get(version["source"], "uploaded")
        detail = {"note": version["note"], "restored_from": version["restored_from__number"]}
        rows.append(DocumentActivity(
            document_id=version["document_id"], actor_id=version["created_by_id"], action=action,
            version_number=version["number"], created_at=version["created_at"],
            detail={key: value for key, value in detail.items() if value},
        ))

    for audit in DocumentTrashAudit.objects.filter(action__in=["trashed", "restored"]).iterator():
        if audit.document_id in existing:
            rows.append(DocumentActivity(
                document_id=audit.document_id, actor_id=audit.actor_id, action=audit.action, created_at=audit.created_at,
            ))

    for audit in ArticlePublicationAudit.objects.iterator():
        if audit.document_id in existing:
            withdrawn = audit.action == "withdrawn"
            rows.append(DocumentActivity(
                document_id=audit.document_id, actor_id=audit.actor_id,
                action="withdrawn" if withdrawn else "published", version_number=audit.version_number,
                created_at=audit.created_at, detail={} if audit.action != "republished" else {"republished": True},
            ))

    DocumentActivity.objects.bulk_create(rows, batch_size=500)


def clear(apps, schema_editor):
    apps.get_model("documents", "DocumentActivity").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("documents", "0007_workspace_favorites_views_activity")]

    operations = [migrations.RunPython(backfill, clear)]
