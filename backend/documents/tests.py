import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connections
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Document, Version
from .services import add_upload


class DocumentTests(TransactionTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage))
        settings.enable()
        self.addCleanup(settings.disable)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)

    def post_file(self, content, name="test.md", url="/api/documents/", **data):
        return self.client.post(url, {"file": SimpleUploadedFile(name, content), **data})

    def test_upload_download_no_overwrite_partial_failure_and_permissions(self):
        html = b"<script>document.write('original')</script>"
        original = self.post_file(html, "test.html")
        self.assertEqual(original.status_code, 201, original.content)
        self.assertEqual(self.post_file(b"\xff").status_code, 400)
        second = self.post_file(b"distinct", "test.html")
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(original.json()["id"], second.json()["id"])
        self.assertEqual(Document.objects.count(), 2)
        self.client.force_login(self.viewer)
        url = f"/api/documents/{original.json()['id']}/"
        response = self.client.get(url + "download/")
        self.assertEqual(b"".join(response.streaming_content), html)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.post_file(b"blocked").status_code, 403)
        self.assertEqual(self.client.patch(url, {}, content_type="application/json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(Client().get(url + "download/").status_code, 403)

    def test_duplicates_force_version_format_storage_and_path_handling(self):
        result = self.post_file(b"same", "../outside.md")
        self.assertEqual(result.status_code, 201, result.content)
        original_id = result.json()["id"]
        self.assertEqual(self.post_file(b"same", "renamed.md").status_code, 409)
        second = self.post_file(b"same", "identical.md", force="true")
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(second.json()["id"], original_id)
        url = f"/api/documents/{original_id}/versions/"
        self.assertEqual(self.post_file(b"other", "other.html", url).status_code, 400)
        self.assertEqual(self.post_file(b"same", "test.md", url).status_code, 409)
        self.assertEqual(self.post_file(b"same", "test.md", url, force="true").json()["current_version"]["number"], 2)
        newer = self.post_file(b"revision", "test.md", url, note="Change")
        self.assertEqual(newer.json()["current_version"]["number"], 3)
        versions = Version.objects.filter(document_id=original_id).order_by("number")
        stored = [(self.storage / version.path).read_bytes() for version in versions]
        self.assertEqual(stored, [b"same", b"same", b"revision"])
        self.assertEqual(versions[0].filename, "outside.md")
        self.assertTrue(all((self.storage / version.path).is_relative_to(self.storage) for version in versions))

    def test_filter_by_html_and_markdown(self):
        html = self.post_file(b"<p>HTML document</p>", "example.html")
        markdown = self.post_file(b"# Markdown document", "example.md")
        self.assertEqual(html.status_code, 201)
        self.assertEqual(markdown.status_code, 201)

        self.client.force_login(self.viewer)
        for file_format, document in (("html", html), ("md", markdown)):
            with self.subTest(file_format=file_format):
                response = self.client.get("/api/documents/", {"file_format": file_format})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item["id"] for item in response.json()["results"]], [document.json()["id"]])

    def test_taxonomy_and_metadata_with_nested_filter(self):
        def create(endpoint, **data):
            response = self.client.post(f"/api/{endpoint}/", data, content_type="application/json")
            self.assertEqual(response.status_code, 201, response.content)
            return response.json()["id"]

        parent = create("categories", name="Parent")
        child = create("categories", name="Child", parent=parent)
        tag = create("tags", name="Tag")
        cycle = self.client.patch(f"/api/categories/{parent}/", {"parent": child}, content_type="application/json")
        self.assertEqual(cycle.status_code, 400)
        response = self.post_file(b"contents", category=child, tags=[tag])
        info = response.json()
        self.assertEqual(info["tags"][0]["id"], tag)
        self.assertEqual(self.client.get("/api/documents/", {"category": parent, "tag": tag}).json()["count"], 1)
        detail = f"/api/documents/{info['id']}/"
        self.assertEqual(self.client.patch(detail, {"title": "New title", "category": None}, content_type="application/json").json()["title"], "New title")
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertEqual(self.client.get(detail + "download/").status_code, 404)
        self.assertTrue(Version.objects.filter(document_id=info["id"]).exists())

    def test_simultaneous_version_uploads_allocate_unique_numbers(self):
        created = self.post_file(b"one").json()
        barrier = Barrier(2)

        def update(content):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                document = add_upload(self.editor, {"file": SimpleUploadedFile("update.md", content), "force": False}, created["id"])
                return document.current_version.number
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = executor.map(update, [b"two", b"three"], timeout=10)
            self.assertEqual(set(results), {2, 3})

    def test_failed_database_write_has_no_document_and_recoverable_file(self):
        data = {"file": SimpleUploadedFile("test.md", b"contents"), "force": False}
        with patch("documents.services.Version.objects.create", side_effect=RuntimeError("write failed")):
            with self.assertRaisesMessage(RuntimeError, "write failed"):
                add_upload(self.editor, data)
        self.assertFalse(Document.objects.exists())
        orphan, = (self.storage / "versions").glob("*/*")
        report = StringIO()
        call_command("check_document_storage", quarantine=True, stdout=report)
        self.assertIn("Unreferenced:", report.getvalue())
        self.assertFalse(orphan.exists())
        self.assertEqual((self.storage / "quarantine" / orphan.relative_to(self.storage)).read_bytes(), b"contents")
