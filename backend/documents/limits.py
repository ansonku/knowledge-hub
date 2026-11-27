"""P23c: per-file size limits, set by admins to any whole MB within a fixed range per kind.

The top of each range is the technical ceiling: nginx allows it (with room for the multipart form), and images
stop at 30 MB because they are decoded and re-encoded in memory. A null setting means the default, which is
what the limits were before they became settings."""
from django.conf import settings

from .models import Document, SiteSettings

MB = 1024 * 1024

# kind: (label, smallest, largest, default) in MB
RANGES = {
    "markdown": ("Markdown 文件", 1, 50, 50),
    "html": ("HTML 文件", 1, 100, 50),
    "image": ("圖片", 1, 30, 10),
    "video": ("影片", 10, 1024, 200),
}
FIELDS = {kind: f"{kind}_max_mb" for kind in RANGES}


def kind_of(document_format):
    return "markdown" if document_format == Document.Format.MARKDOWN else "html"


def megabytes(kind, site=None):
    value = getattr(site or SiteSettings.current(), FIELDS[kind])
    return value or RANGES[kind][3]


def max_bytes(kind, site=None):
    return megabytes(kind, site) * MB


def ceiling(kind):
    return RANGES[kind][2] * MB


def size_text(mb):
    return f"{mb // 1024} GB" if mb >= 1024 and mb % 1024 == 0 else f"{mb} MB"


def too_big(kind, site=None):
    """The message for a file over the limit, e.g. 「影片超過上限 200 MB。」"""
    return f"{RANGES[kind][0]}超過上限 {size_text(megabytes(kind, site))}。"


def for_members():
    """What the browser checks before sending (P23c), with the batch size."""
    site = SiteSettings.current()
    return {**{f"{kind}_bytes": max_bytes(kind, site) for kind in RANGES}, "batch": settings.DOCUMENT_MAX_BATCH}


def for_admins():
    site = SiteSettings.current()
    return {
        kind: {"label": label, "mb": megabytes(kind, site), "min": low, "max": high, "default": default}
        for kind, (label, low, high, default) in RANGES.items()
    }
