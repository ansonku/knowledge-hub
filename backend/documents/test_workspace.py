import importlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import ArticlePublication, Category, Document, DocumentActivity, DocumentView, Favorite, Tag

backfill = importlib.import_module("documents.migrations.0008_backfill_document_activity").backfill


class WorkspaceTests(TransactionTestCase):
    """P2 member workspace APIs: favourites, recent views, activity, list filters and bulk changes."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)

    def upload(self, content, name="doc.md", **data):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile(name, content), **data})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def as_user(self, user):
        client = Client()
        client.force_login(user)
        return client

    def listing(self, client=None, **params):
        response = (client or self.client).get("/api/documents/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    # ---- favourites -----------------------------------------------------------

    def test_favorites_are_private_idempotent_and_filterable(self):
        first, second = self.upload(b"one"), self.upload(b"two")
        viewer = self.as_user(self.viewer)
        url = f"/api/documents/{first}/favorite/"
        self.assertEqual(viewer.put(url).status_code, 204)
        self.assertEqual(viewer.put(url).status_code, 204)
        self.assertEqual(Favorite.objects.filter(user=self.viewer).count(), 1)
        self.assertEqual([row["id"] for row in self.listing(viewer, favorite="1")], [first])
        self.assertTrue(viewer.get(f"/api/documents/{first}/").json()["is_favorite"])
        # Another member never sees the viewer's favourites.
        self.assertEqual(self.listing(favorite="1"), [])
        self.assertFalse(next(row for row in self.listing() if row["id"] == first)["is_favorite"])
        self.assertEqual(viewer.delete(url).status_code, 204)
        self.assertEqual(viewer.delete(url).status_code, 204)
        self.assertEqual(self.listing(viewer, favorite="1"), [])
        self.assertEqual(Client().put(url).status_code, 403)
        self.client.delete(f"/api/documents/{second}/")
        self.assertEqual(viewer.put(f"/api/documents/{second}/favorite/").status_code, 404)

    # ---- recent views ---------------------------------------------------------

    def test_recent_views_are_private_ordered_pruned_and_skip_trash(self):
        ids = [self.upload(f"doc {index}".encode()) for index in range(4)]
        viewer = self.as_user(self.viewer)
        for document_id in (ids[0], ids[1], ids[2], ids[0]):
            self.assertEqual(viewer.post(f"/api/documents/{document_id}/view/").status_code, 204)
        recent = viewer.get("/api/me/recent/").json()["results"]
        self.assertEqual([row["id"] for row in recent], [ids[0], ids[2], ids[1]])
        self.assertIn("viewed_at", recent[0])
        self.assertEqual(self.client.get("/api/me/recent/").json()["results"], [])
        self.client.delete(f"/api/documents/{ids[2]}/")
        self.assertEqual([row["id"] for row in viewer.get("/api/me/recent/").json()["results"]], [ids[0], ids[1]])
        self.assertEqual(viewer.get("/api/me/recent/", {"limit": 1}).json()["results"][0]["id"], ids[0])
        self.assertEqual(viewer.get("/api/me/recent/", {"limit": 0}).status_code, 400)
        with patch("documents.views.RECENT_LIMIT", 2):
            viewer.post(f"/api/documents/{ids[3]}/view/")
        self.assertEqual(DocumentView.objects.filter(user=self.viewer).count(), 2)
        self.assertEqual(Client().get("/api/me/recent/").status_code, 403)
        self.assertEqual(Client().post(f"/api/documents/{ids[0]}/view/").status_code, 403)

    # ---- activity -------------------------------------------------------------

    def test_activity_records_versions_metadata_trash_and_publication(self):
        category = Category.objects.create(name="Backend")
        tag = Tag.objects.create(name="API")
        document_id = self.upload(b"# Spec", note="first")
        self.client.post(f"/api/documents/{document_id}/versions/", {"file": SimpleUploadedFile("doc.md", b"# Spec v2"), "note": "second"})
        self.client.patch(f"/api/documents/{document_id}/", {"title": "Spec", "category": str(category.pk), "tags": [str(tag.pk)]}, content_type="application/json")
        self.client.patch(f"/api/documents/{document_id}/", {"title": "Spec"}, content_type="application/json")
        admin = self.as_user(self.admin)
        version = Document.objects.get(pk=document_id).current_version_id
        self.assertEqual(admin.post(f"/api/documents/{document_id}/publication/", {"version": str(version), "title": "Spec"}, content_type="application/json").status_code, 200)
        self.assertEqual(admin.delete(f"/api/documents/{document_id}/publication/").status_code, 204)

        viewer = self.as_user(self.viewer)
        feed = viewer.get(f"/api/documents/{document_id}/activity/").json()["results"]
        self.assertEqual([item["action"] for item in feed], ["withdrawn", "published", "metadata", "uploaded", "created"])
        self.assertEqual(feed[2]["detail"]["category"], {"from": None, "to": "Backend"})
        self.assertEqual(feed[2]["detail"]["tags"], {"added": ["API"], "removed": []})
        self.assertEqual(feed[3]["detail"]["note"], "second")
        self.assertEqual(feed[3]["actor"], "editor")
        self.assertEqual(feed[1]["version_number"], 2)

        self.assertEqual([item["action"] for item in viewer.get("/api/activity/", {"scope": "publish"}).json()["results"]], ["withdrawn", "published"])
        mine = admin.get("/api/activity/", {"scope": "mine"}).json()["results"]
        self.assertTrue(mine and all(item["action"] in ("published", "withdrawn") for item in mine))
        self.assertEqual(viewer.get("/api/activity/", {"scope": "other"}).status_code, 400)

        # Trashed documents drop out of every feed; restoring brings them back with a new event.
        self.client.delete(f"/api/documents/{document_id}/")
        self.assertEqual(viewer.get("/api/activity/").json()["results"], [])
        self.assertEqual(viewer.get(f"/api/documents/{document_id}/activity/").status_code, 404)
        self.client.post(f"/api/trash/{document_id}/restore/")
        self.assertEqual(viewer.get("/api/activity/").json()["results"][0]["action"], "restored")
        self.assertEqual(Client().get("/api/activity/").status_code, 403)

    def test_activity_pages(self):
        document_id = self.upload(b"start")
        for index in range(22):
            self.client.patch(f"/api/documents/{document_id}/", {"title": f"Title {index}"}, content_type="application/json")
        first = self.client.get("/api/activity/").json()
        self.assertEqual((len(first["results"]), first["has_more"]), (20, True))
        second = self.client.get("/api/activity/", {"page": 2}).json()
        self.assertEqual((len(second["results"]), second["has_more"]), (3, False))

    def test_backfill_seeds_versions_trash_and_publication_history(self):
        document_id = self.upload(b"seed")
        self.client.post(f"/api/documents/{document_id}/versions/", {"file": SimpleUploadedFile("doc.md", b"seed 2")})
        self.client.delete(f"/api/documents/{document_id}/")
        self.client.post(f"/api/trash/{document_id}/restore/")
        DocumentActivity.objects.all().delete()
        backfill(apps, None)
        actions = sorted(DocumentActivity.objects.filter(document_id=document_id).values_list("action", flat=True))
        self.assertEqual(actions, ["created", "restored", "trashed", "uploaded"])

    # ---- list filters and fields ----------------------------------------------

    def test_visibility_ordering_and_publication_fields(self):
        public = self.upload(b"public", title="B public")
        lagging = self.upload(b"lagging", title="A lagging")
        private = self.upload(b"private", title="C private")
        admin = self.as_user(self.admin)
        for document_id in (public, lagging):
            document = Document.objects.get(pk=document_id)
            admin.post(f"/api/documents/{document_id}/publication/", {"version": str(document.current_version_id), "title": document.title}, content_type="application/json")
        self.client.post(f"/api/documents/{lagging}/versions/", {"file": SimpleUploadedFile("doc.md", b"lagging v2")})
        viewer = self.as_user(self.viewer)
        rows = {row["id"]: row for row in self.listing(viewer)}
        self.assertEqual((rows[lagging]["published_version"], rows[lagging]["current_version"]["number"]), (1, 2))
        self.assertIsNone(rows[private]["published_version"])

        def ids(**params):
            return [row["id"] for row in self.listing(viewer, **params)]

        self.assertEqual(ids(visibility="lagging"), [lagging])
        self.assertEqual(set(ids(visibility="public")), {public, lagging})
        self.assertEqual(ids(visibility="private"), [private])
        self.assertEqual(ids(ordering="title"), [lagging, public, private])
        self.assertEqual(ids(ordering="-title"), [private, public, lagging])
        self.assertEqual(viewer.get("/api/documents/", {"ordering": "size"}).status_code, 400)
        self.assertEqual(viewer.get("/api/documents/", {"visibility": "secret"}).status_code, 400)

    def test_category_counts_description_color_and_limits(self):
        parent = self.client.post("/api/categories/", {"name": "Tech", "description": "Specs", "color": "teal"}, content_type="application/json")
        self.assertEqual(parent.status_code, 201, parent.content)
        category_id = parent.json()["id"]
        self.assertEqual(self.client.post("/api/categories/", {"name": "Bad", "color": "neon"}, content_type="application/json").status_code, 400)
        self.upload(b"in tech", category=category_id)
        trashed = self.upload(b"trashed", category=category_id)
        self.client.delete(f"/api/documents/{trashed}/")
        category = next(item for item in self.as_user(self.viewer).get("/api/categories/").json() if item["id"] == category_id)
        self.assertEqual((category["document_count"], category["description"], category["color"]), (1, "Specs", "teal"))
        self.assertEqual(self.as_user(self.viewer).patch(f"/api/categories/{category_id}/", {"description": "x"}, content_type="application/json").status_code, 403)
        limits = self.client.get("/api/auth/me").json()["limits"]
        self.assertEqual(set(limits), {"bytes", "batch"})

    # ---- bulk changes -----------------------------------------------------------

    def test_bulk_changes_require_editor_and_apply_atomically(self):
        category = Category.objects.create(name="Ops")
        keep, drop = Tag.objects.create(name="keep"), Tag.objects.create(name="drop")
        first, second = self.upload(b"first"), self.upload(b"second")
        Document.objects.get(pk=first).tags.set([drop])

        def post(client, **data):
            return client.post("/api/documents/bulk/", data, content_type="application/json")

        self.assertEqual(post(self.as_user(self.viewer), ids=[first], action="trash").status_code, 403)
        self.assertEqual(post(Client(), ids=[first], action="trash").status_code, 403)

        self.assertEqual(post(self.client, ids=[first, second], action="move", category=str(category.pk)).json(), {"count": 2})
        self.assertEqual(Document.objects.filter(category=category).count(), 2)
        post(self.client, ids=[first, second], action="add_tags", tags=[str(keep.pk)])
        post(self.client, ids=[first, second], action="remove_tags", tags=[str(drop.pk)])
        for document_id in (first, second):
            self.assertEqual(list(Document.objects.get(pk=document_id).tags.values_list("name", flat=True)), ["keep"])
        self.assertTrue(DocumentActivity.objects.filter(document_id=first, action="metadata", detail__tags__removed=["drop"]).exists())

        # A missing document rejects the whole request without partial changes.
        missing = post(self.client, ids=[first, "00000000-0000-0000-0000-000000000000"], action="move", category=None)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(Document.objects.get(pk=first).category, category)
        self.assertEqual(post(self.client, ids=[first], action="move").status_code, 400)
        self.assertEqual(post(self.client, ids=[first], action="add_tags", tags=[]).status_code, 400)
        self.assertEqual(post(self.client, ids=[first] * 101, action="trash").status_code, 400)

        admin = self.as_user(self.admin)
        document = Document.objects.get(pk=first)
        admin.post(f"/api/documents/{first}/publication/", {"version": str(document.current_version_id), "title": document.title}, content_type="application/json")
        self.assertTrue(ArticlePublication.objects.filter(document_id=first).exists())
        self.assertEqual(post(self.client, ids=[first, second], action="trash").json(), {"count": 2})
        self.assertEqual(Document.objects.filter(is_trashed=True).count(), 2)
        self.assertFalse(ArticlePublication.objects.filter(document_id=first).exists())
