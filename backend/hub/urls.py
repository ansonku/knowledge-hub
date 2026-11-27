from django.urls import include, path

from documents.preview import html_preview
from users import setup
from documents.publication import public_article_page, public_site_page

from . import onboarding
from .audit import audit_feed
from .maintenance import run_maintenance
from .system import system_status
from .views import health, site_root

urlpatterns = [
    path("", site_root, name="site_root"),
    path("api/health", health, name="health"),
    path("api/setup/", setup.setup_status, name="setup_status"),
    path("api/setup/verify", setup.setup_verify, name="setup_verify"),
    path("api/setup/complete", setup.setup_complete, name="setup_complete"),
    path("api/admin/audit/", audit_feed, name="audit_feed"),
    path("api/admin/system/", system_status, name="system_status"),
    path("api/admin/about/", onboarding.about_page, name="about_page"),
    path("api/admin/getting-started/", onboarding.getting_started, name="getting_started"),
    path("api/admin/system/maintenance/", run_maintenance, name="run_maintenance"),
    path("articles/", public_site_page),
    path("articles/<uuid:document_id>/", public_article_page),
    path("", include("users.urls")),
    path("api/", include("documents.urls")),
    path("preview/<slug:token>/", html_preview, name="html-preview"),
]
