import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Category, Document


class ReadingPortalTests(TransactionTestCase):
    """P5d: the member reading portal API (/api/read/...)."""

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
        self.parent = Category.objects.create(name="Ops", color="teal")
        self.child = Category.objects.create(name="Runbooks", parent=self.parent, color="blue")

    def upload(self, content, name="doc.md", **data):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile(name, content), **data})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def reader(self):
        client = Client()
        client.force_login(self.viewer)
        return client

    def test_members_only(self):
        visitor = Client()
        document = self.upload(b"x")
        for url in ("/api/read/nav/", "/api/read/articles/", f"/api/read/articles/{document}/"):
            self.assertEqual(visitor.get(url).status_code, 403, url)
            self.assertEqual(self.reader().get(url).status_code, 200, url)

    def test_lists_every_readable_document_with_visibility(self):
        private = self.upload(b"# Private\n\nInternal runbook text", title="Private", category=str(self.child.pk))
        public = self.upload(b"Public body", title="Public", category=str(self.parent.pk))
        trashed = self.upload(b"gone", title="Trashed", category=str(self.child.pk))
        document = Document.objects.get(pk=public)
        admin = Client()
        admin.force_login(self.admin)
        admin.post(f"/api/documents/{public}/publication/", {"version": str(document.current_version_id), "title": "Public"},
                   content_type="application/json")
        self.client.delete(f"/api/documents/{trashed}/")
        reader = self.reader()

        nav = reader.get("/api/read/nav/").json()
        self.assertEqual({row["document_id"] for row in nav["articles"]}, {private, public})
        self.assertEqual([(node["name"], node["article_count"], node["total_count"]) for node in nav["collections"]],
                         [("Ops", 1, 2), ("Runbooks", 1, 1)])

        cards = {card["document_id"]: card for card in reader.get("/api/read/articles/").json()["results"]}
        self.assertEqual(set(cards), {private, public})
        self.assertFalse(cards[private]["public"])
        self.assertTrue(cards[public]["public"])
        self.assertEqual([node["name"] for node in cards[private]["path"]], ["Ops", "Runbooks"])
        self.assertEqual(cards[private]["excerpt"], "Internal runbook text")
        by_parent = reader.get("/api/read/articles/", {"collection": str(self.parent.pk)}).json()["results"]
        self.assertEqual({card["document_id"] for card in by_parent}, {private, public})
        found = reader.get("/api/read/articles/", {"q": "runbook"}).json()["results"]
        self.assertEqual([card["document_id"] for card in found], [private])

        article = reader.get(f"/api/read/articles/{private}/").json()
        self.assertEqual(article["body"], "# Private\n\nInternal runbook text")
        self.assertFalse(article["public"])
        self.assertEqual(article["version_number"], 1)
        self.assertEqual(reader.get(f"/api/read/articles/{trashed}/").status_code, 404)

    def test_html_is_the_sanitised_reading_copy(self):
        page = b"<html><body><h1>Title</h1><p onclick='x()'>Body</p><script>alert(1)</script></body></html>"
        document = self.upload(page, name="page.html", title="Page")
        body = self.reader().get(f"/api/read/articles/{document}/").json()["body"]
        self.assertIn("Body", body)
        for unsafe in ("<script", "alert(1)", "onclick"):
            self.assertNotIn(unsafe, body)
