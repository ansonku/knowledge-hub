from django.urls import include, path

from documents.preview import html_preview
from documents.publication import public_article_page, public_site_page

from .views import health, site_root

urlpatterns = [
    path("", site_root, name="site_root"),
    path("api/health", health, name="health"),
    path("articles/", public_site_page),
    path("articles/<uuid:document_id>/", public_article_page),
    path("", include("users.urls")),
    path("api/", include("documents.urls")),
    path("preview/<slug:token>/", html_preview, name="html-preview"),
]
