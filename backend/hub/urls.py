from django.urls import include, path

from documents.preview import html_preview
from documents.publication import public_article_page

from .views import health

urlpatterns = [
    path("api/health", health, name="health"),
    path("articles/<uuid:document_id>/", public_article_page),
    path("", include("users.urls")),
    path("api/", include("documents.urls")),
    path("preview/<slug:token>/", html_preview, name="html-preview"),
]
