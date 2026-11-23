from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import preview, views

router = SimpleRouter()
router.register("categories", views.CategoryViewSet)
router.register("tags", views.TagViewSet)

urlpatterns = [
    path("documents/", views.documents),
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
