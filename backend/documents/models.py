import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Lower, Upper


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "parent", nulls_distinct=False, name="unique_category_sibling"),
        ]


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(Lower("name"), name="unique_tag_name")]


class Document(models.Model):
    class Format(models.TextChoices):
        HTML = "html", "HTML"
        MARKDOWN = "md", "Markdown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=240)
    format = models.CharField(max_length=4, choices=Format.choices)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    tags = models.ManyToManyField(Tag, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    current_version = models.ForeignKey("Version", null=True, on_delete=models.PROTECT, related_name="+")
    is_trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Version(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    path = models.CharField(max_length=128, unique=True)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    search_text = models.TextField(null=True, editable=False)
    size = models.PositiveBigIntegerField()
    note = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=16, default="upload", editable=False)
    restored_from = models.ForeignKey("self", null=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="unique_document_version")]
        indexes = [GinIndex(OpClass(Upper("search_text"), name="gin_trgm_ops"), name="version_search_trgm")]


class PreviewTicket(models.Model):
    digest = models.CharField(primary_key=True, max_length=64)
    version = models.ForeignKey(Version, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session_version = models.PositiveBigIntegerField()
    expires_at = models.DateTimeField(db_index=True)

    allow_historical = models.BooleanField(default=False)


class VersionRestoreAudit(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="restore_audits")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    restored_from = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="+")
    previous_version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="+")
    new_version = models.OneToOneField(Version, on_delete=models.CASCADE, related_name="restore_audit")
    created_at = models.DateTimeField(auto_now_add=True)


class DocumentTrashAudit(models.Model):
    document_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=16)
    version_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class PendingDocumentDeletion(models.Model):
    document_id = models.UUIDField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
