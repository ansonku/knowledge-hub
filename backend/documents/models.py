import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Lower, Upper
from django.utils import timezone


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
    # P22: a picture of this document shown on cards (and as og:image when published). A document setting, not
    # part of any version. Cleared when the picture goes.
    cover_image = models.ForeignKey("DocumentImage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tags = models.ManyToManyField(Tag, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    current_version = models.ForeignKey("Version", null=True, on_delete=models.PROTECT, related_name="+")
    is_trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # P11c: a Markdown document can read as a photo album. Not versioned; it applies to the public article too.
    class Presentation(models.TextChoices):
        ARTICLE = "article", "文章"
        GALLERY = "gallery", "相簿"

    class GalleryLayout(models.TextChoices):
        DEFAULT = "", "跟隨系統預設"
        JUSTIFIED = "justified", "齊邊"
        GRID = "grid", "方格"
        MASONRY = "masonry", "瀑布流"
        VERTICAL = "vertical", "直列"
        CAROUSEL = "carousel", "輪播"

    presentation = models.CharField(max_length=8, choices=Presentation.choices, default=Presentation.ARTICLE)
    gallery_layout = models.CharField(max_length=12, choices=GalleryLayout.choices, default="", blank=True)


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
    # SET_NULL so an Admin can delete the source version; the number keeps "還原自 v3" readable afterwards.
    restored_from = models.ForeignKey("self", null=True, on_delete=models.SET_NULL, related_name="+")
    restored_from_number = models.PositiveIntegerField(null=True, editable=False)
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
    # Deleting a version must never delete this audit: the links go, the numbers stay.
    restored_from = models.ForeignKey(Version, null=True, on_delete=models.SET_NULL, related_name="+")
    previous_version = models.ForeignKey(Version, null=True, on_delete=models.SET_NULL, related_name="+")
    new_version = models.OneToOneField(Version, null=True, on_delete=models.SET_NULL, related_name="restore_audit")
    restored_from_number = models.PositiveIntegerField(null=True)
    previous_number = models.PositiveIntegerField(null=True)
    new_number = models.PositiveIntegerField(null=True)
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
        FEATURED = "featured", "Featured on the public home"
        UNFEATURED = "unfeatured", "Removed from the public home"
        VERSION_DELETED = "version_deleted", "Deleted a version"

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

    # Announcement banner (P6c): plain text, shown on every page while switched on and inside its window.
    class NoticeLevel(models.TextChoices):
        INFO = "info", "資訊"
        WARNING = "warning", "提醒"
        URGENT = "urgent", "重要"

    notice_enabled = models.BooleanField(default=False)
    notice_text = models.CharField(max_length=120, blank=True)
    notice_link = models.CharField(max_length=300, blank=True)
    notice_level = models.CharField(max_length=8, choices=NoticeLevel.choices, default=NoticeLevel.INFO)
    notice_starts_at = models.DateTimeField(null=True, blank=True)
    notice_ends_at = models.DateTimeField(null=True, blank=True)
    notice_updated_at = models.DateTimeField(null=True, blank=True)

    # P11d: how pictures open and galleries lay out, site-wide. Only choices, no raw timings (decision 27).
    class LightboxEffect(models.TextChoices):
        CENTER = "center", "背景先出、圖片從中間浮現"
        ZOOM = "zoom", "從縮圖放大"
        FADE = "fade", "淡入"

    class LightboxSpeed(models.TextChoices):
        FAST = "fast", "快"
        NORMAL = "normal", "標準"
        SLOW = "slow", "慢"

    lightbox_effect = models.CharField(max_length=8, choices=LightboxEffect.choices, default=LightboxEffect.CENTER)
    lightbox_speed = models.CharField(max_length=8, choices=LightboxSpeed.choices, default=LightboxSpeed.NORMAL)
    # Backdrop opacity in percent, 60–100.
    lightbox_backdrop = models.PositiveSmallIntegerField(default=92)
    gallery_layout = models.CharField(
        max_length=12, default="justified",
        choices=[(value, label) for value, label in Document.GalleryLayout.choices if value],
    )
    member_download = models.BooleanField(default=True)
    # Skip the animation when the browser asks for reduced motion. Off for sites whose readers sit on virtual
    # desktops, where browsers often report reduced motion although nobody asked for it.
    lightbox_reduced_motion = models.BooleanField(default=True)
    # P20: seconds between pictures when the lightbox plays them as a slideshow.
    lightbox_interval = models.PositiveSmallIntegerField(default=5, choices=[(3, "3 秒"), (5, "5 秒"), (8, "8 秒"), (12, "12 秒")])

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="site_settings_singleton")]

    def active_notice(self, now=None):
        """The announcement to show right now, or None. Its id changes whenever it is edited."""
        now = now or timezone.now()
        if not (self.notice_enabled and self.notice_text):
            return None
        if (self.notice_starts_at and now < self.notice_starts_at) or (self.notice_ends_at and now >= self.notice_ends_at):
            return None
        return {
            "id": f"{self.notice_updated_at.timestamp():.6f}" if self.notice_updated_at else "0",
            "text": self.notice_text, "link": self.notice_link, "level": self.notice_level,
        }

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


class FeaturedArticle(models.Model):
    """P6b: published articles an Admin pins to the public home, in order (at most four)."""
    document = models.OneToOneField(Document, primary_key=True, on_delete=models.CASCADE, related_name="+")
    position = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]



class DocumentImage(models.Model):
    """An image pasted into a Markdown document. It belongs to that one document and follows its access rules."""

    class Format(models.TextChoices):
        PNG = "png", "PNG"
        JPEG = "jpeg", "JPEG"
        GIF = "gif", "GIF"
        WEBP = "webp", "WebP"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="images")
    # Digest of the re-encoded bytes that are stored and served.
    sha256 = models.CharField(max_length=64)
    format = models.CharField(max_length=8, choices=Format.choices)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    size = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    # Pasting the same picture again refreshes this; the 24-hour grace before an unused image is removed counts from it.
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "sha256"], name="unique_document_image")]
        indexes = [models.Index(fields=["uploaded_at"], name="document_image_uploaded")]

    @property
    def path(self):
        return f"images/{self.document_id}/{self.pk}.{self.format}"


class VersionImage(models.Model):
    """A version's Markdown refers to this image. An image is removable only once no version refers to it."""

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="image_references")
    # RESTRICT: a referenced image can only go away together with the versions that use it.
    image = models.ForeignKey(DocumentImage, on_delete=models.RESTRICT, related_name="references")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "image"], name="unique_version_image")]


class DocumentVideo(models.Model):
    """A video embedded in a Markdown document. Like DocumentImage, it belongs to one document and follows its access
    rules; the bytes are stored as uploaded (no transcoding) and nginx serves them after Django checks access."""

    class Format(models.TextChoices):
        MP4 = "mp4", "MP4"
        WEBM = "webm", "WebM"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="videos")
    sha256 = models.CharField(max_length=64)
    format = models.CharField(max_length=8, choices=Format.choices)
    size = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    # Uploading the same file again refreshes this; the 24-hour grace before an unused video is removed counts from it.
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "sha256"], name="unique_document_video")]
        indexes = [models.Index(fields=["uploaded_at"], name="document_video_uploaded")]

    @property
    def path(self):
        return f"videos/{self.document_id}/{self.pk}.{self.format}"


class VersionVideo(models.Model):
    """A version's Markdown refers to this video. A video is removable only once no version refers to it."""

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="video_references")
    # RESTRICT: a referenced video can only go away together with the versions that use it.
    video = models.ForeignKey(DocumentVideo, on_delete=models.RESTRICT, related_name="references")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "video"], name="unique_version_video")]


class VersionLink(models.Model):
    """P13: a version's Markdown links to another document. The target is kept as a bare id (no foreign key),
    so a link to a document that was permanently deleted still shows up as broken."""

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="link_references")
    target_id = models.UUIDField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "target_id"], name="unique_version_link")]
