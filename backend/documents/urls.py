from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import preview, publication, reading, views

router = SimpleRouter()
router.register("categories", views.CategoryViewSet)
router.register("tags", views.TagViewSet)

urlpatterns = [
    path("public/articles/", publication.public_articles),
    path("site/", views.site_settings),
    path("public/collections/", publication.public_collections),
    path("public/nav/", publication.public_nav),
    path("read/nav/", reading.read_nav),
    path("read/articles/", reading.read_articles),
    path("read/articles/<uuid:document_id>/", reading.read_article),
    path("public/articles/<uuid:document_id>/", publication.public_article),
    path("documents/<uuid:document_id>/publication/", publication.manage_publication),
    path("documents/", views.documents),
    path("documents/bulk/", views.bulk),
    path("documents/<uuid:document_id>/favorite/", views.favorite),
    path("documents/<uuid:document_id>/view/", views.record_view),
    path("documents/<uuid:document_id>/activity/", views.document_activity),
    path("activity/", views.activity_feed),
    path("me/recent/", views.recent),
    path("trash/", views.trash_list),
    path("trash/<uuid:document_id>/restore/", views.restore_trashed_document),
    path("trash/<uuid:document_id>/delete/", views.delete_trashed_document),
    path("documents/<uuid:document_id>/", views.document_detail),
    path("documents/<uuid:document_id>/versions/", views.new_version),
    path("documents/<uuid:document_id>/versions/<uuid:version_id>/", views.version_detail),
    path("documents/<uuid:document_id>/versions/<uuid:version_id>/download/", views.download_version),
    path("documents/<uuid:document_id>/versions/<uuid:version_id>/preview/", preview.issue_preview),
    path("documents/<uuid:document_id>/versions/<uuid:version_id>/restore/", views.restore_version),
    path("documents/<uuid:document_id>/markdown/", views.new_version, {"edit": True}),
    path("documents/<uuid:document_id>/download/", views.download),
    path("documents/<uuid:document_id>/preview/", preview.issue_preview),
    path("", include(router.urls)),
]
