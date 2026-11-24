from django.urls import include, path

from documents.preview import html_preview
from documents.publication import public_article_page, public_site_page

from .audit import audit_feed
from .system import system_status
from .views import health, site_root

urlpatterns = [
    path("", site_root, name="site_root"),
    path("api/health", health, name="health"),
    path("api/admin/audit/", audit_feed, name="audit_feed"),
    path("api/admin/system/", system_status, name="system_status"),
    path("articles/", public_site_page),
    path("articles/<uuid:document_id>/", public_article_page),
    path("", include("users.urls")),
    path("api/", include("documents.urls")),
    path("preview/<slug:token>/", html_preview, name="html-preview"),
]
