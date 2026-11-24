import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Lower, Upper


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    description = models.TextField(max_length=1000, blank=True)
    color = models.CharField(max_length=8, blank=True, choices=[
        (name, name) for name in ("blue", "teal", "green", "amber", "orange", "red", "purple", "gray")
    ])

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "parent", nulls_distinct=False, name="unique_category_sibling"),
        ]


# Order used when a collection is created without choosing a colour (gray stays a deliberate choice).
AUTO_COLLECTION_COLORS = ("blue", "teal", "green", "amber", "orange", "red", "purple")


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


class ArticlePublication(models.Model):
    document = models.OneToOneField(Document, primary_key=True, on_delete=models.CASCADE)
    version = models.ForeignKey(Version, on_delete=models.CASCADE)
    title = models.CharField(max_length=240)
    format = models.CharField(max_length=4, choices=Document.Format.choices)
    body = models.TextField()
    search_text = models.TextField()
    published_at = models.DateTimeField(auto_now=True)


class ArticlePublicationAudit(models.Model):
    document_id = models.UUIDField(db_index=True)
    version_id = models.UUIDField()
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)


class Favorite(models.Model):
    """A member's bookmarked document; private to that member."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint("user", "document", name="unique_favorite")]
        indexes = [models.Index(fields=["user", "-created_at"], name="favorite_user_recent")]


class DocumentView(models.Model):
    """The last time a member opened a document; private to that member."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="+")
    viewed_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint("user", "document", name="unique_document_view")]
        indexes = [models.Index(fields=["user", "-viewed_at"], name="document_view_user_recent")]


class DocumentActivity(models.Model):
    """Unified activity feed for a document. Rows go away with the document on permanent deletion."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPLOADED = "uploaded", "Uploaded version"
        EDITED = "edited", "Edited Markdown"
        RESTORED_VERSION = "restored_version", "Restored version"
        METADATA = "metadata", "Changed details"
        TRASHED = "trashed", "Moved to trash"
        RESTORED = "restored", "Restored from trash"
        PUBLISHED = "published", "Published"
        WITHDRAWN = "withdrawn", "Withdrawn"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=20, choices=Action.choices)
    version_number = models.PositiveIntegerField(null=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["document", "-created_at"], name="activity_document_recent")]


class SiteSettings(models.Model):
    """Site-wide name and tagline (one row, pk=1). Shown on the public site, the workspace and in SEO."""
    DEFAULT_NAME = "Knowledge Hub"
    DEFAULT_TAGLINE = "團隊成員撰寫並審核後公開的技術規範、操作指南與參考文件。"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=60, default=DEFAULT_NAME)
    tagline = models.CharField(max_length=160, default=DEFAULT_TAGLINE, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="site_settings_singleton")]

    @classmethod
    def current(cls):
        return cls.objects.filter(pk=1).first() or cls()


class ArticleViewDaily(models.Model):
    """Public article views per day: a count only, never who viewed (decision 15)."""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="+")
    day = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint("document", "day", name="unique_article_view_day")]
        indexes = [models.Index(fields=["day"], name="article_view_day")]

