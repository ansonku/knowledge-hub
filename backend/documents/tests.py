import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connections
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from users.models import User

from .models import Document, PreviewTicket, Version
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

    def issue_preview(self, document, client=None, **headers):
        return (client or self.client).post(
            f"/api/documents/{document['id']}/preview/", {"version": document["current_version"]["id"]},
            content_type="application/json", HTTP_HOST="localhost", **headers,
        )

    @override_settings(LOCAL_HTML_PREVIEW=True, PUBLIC_ORIGIN="http://localhost:18080")
    def test_preview_ticket_requires_login_csrf_and_correct_version(self):
        document = self.post_file(b"<p>Example</p>", "example.html").json()
        endpoint = f"/api/documents/{document['id']}/preview/"
        anonymous = Client()
        self.assertEqual(self.issue_preview(document, anonymous).status_code, 403)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.viewer)
        self.assertEqual(self.issue_preview(document, browser).status_code, 403)
        csrf = browser.get("/api/auth/me", HTTP_HOST="localhost").json()["csrf_token"]
        denied = browser.post(
            endpoint, {"version": "unknown"}, content_type="application/json",
            HTTP_HOST="localhost", HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(self.issue_preview(document, browser, HTTP_X_CSRFTOKEN=csrf).status_code, 201)

    @override_settings(LOCAL_HTML_PREVIEW=True, PUBLIC_ORIGIN="http://localhost:18080")
    def test_direct_preview_is_sandboxed_and_the_ticket_is_single_use(self):
        content = b"<!doctype html><h1>Sample HTML</h1>"
        document = self.post_file(content, "example.html").json()
        issued = self.issue_preview(document)
        self.assertEqual(issued.status_code, 201, issued.content)
        self.assertIn("no-store", issued["Cache-Control"])
        path = issued.json()["url"]
        browser = Client()
        response = browser.get(path, HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), content)
        policy = response["Content-Security-Policy"]
        for directive in ("sandbox allow-scripts", "default-src 'none'", "connect-src 'none'", "form-action 'none'", "frame-ancestors 'self'"):
            self.assertIn(directive, policy)
        self.assertNotIn("allow-same-origin", policy)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(response.cookies)
        self.assertEqual(browser.get(path, HTTP_HOST="localhost").status_code, 404)

    @override_settings(LOCAL_HTML_PREVIEW=True, PUBLIC_ORIGIN="http://localhost:18080")
    def test_preview_denies_expired_revoked_and_nonlocal_requests(self):
        document = self.post_file(b"<p>Example</p>", "example.html").json()
        endpoint = f"/api/documents/{document['id']}/"
        path = self.issue_preview(document).json()["url"]
        PreviewTicket.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(path, HTTP_HOST="localhost").status_code, 404)
        self.assertEqual(self.issue_preview(document, HTTP_CF_CONNECTING_IP="198.51.100.10").status_code, 404)
        self.assertEqual(self.issue_preview(document, HTTP_X_FORWARDED_PROTO="https").status_code, 404)
        with override_settings(PUBLIC_ORIGIN="https://hub.example.test"):
            self.assertEqual(self.issue_preview(document).status_code, 404)
        path = self.issue_preview(document).json()["url"]
        self.assertEqual(self.client.delete(endpoint, HTTP_HOST="localhost").status_code, 204)
        self.assertEqual(self.client.get(path, HTTP_HOST="localhost").status_code, 404)

    @override_settings(LOCAL_HTML_PREVIEW=True, PUBLIC_ORIGIN="http://localhost:18080")
    def test_opaque_and_cross_site_reads_are_denied_even_with_a_session(self):
        url = "/api/documents/"
        for headers in ({"HTTP_ORIGIN": "null"}, {"HTTP_SEC_FETCH_SITE": "cross-site"}):
            response = self.client.get(url, **headers)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(self.client.get(url, HTTP_SEC_FETCH_SITE="same-origin").status_code, 200)

    def test_markdown_edit_keeps_original_and_detects_conflicts(self):
        original = self.post_file(b"# Original", "article.md").json()
        endpoint = f"/api/documents/{original['id']}/markdown/"
        original_version = original["current_version"]["id"]

        viewer = Client()
        viewer.force_login(self.viewer)
        blocked = viewer.post(endpoint, {
            "file": SimpleUploadedFile("article.md", b"# Viewer edit"),
            "base_version": original_version,
        })
        self.assertEqual(blocked.status_code, 403)

        editor = Client(enforce_csrf_checks=True)
        editor.force_login(self.editor)
        payload = {"base_version": original_version, "note": "Clarify"}
        self.assertEqual(editor.post(endpoint, {
            **payload, "file": SimpleUploadedFile("renamed.md", b"# Updated"),
        }).status_code, 403)
        token = editor.get("/api/auth/me").json()["csrf_token"]
        saved = editor.post(endpoint, {
            **payload, "file": SimpleUploadedFile("renamed.md", b"# Updated"),
        }, headers={"X-CSRFToken": token})
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.json()["current_version"]["number"], 2)
        self.assertEqual(saved.json()["current_version"]["filename"], "article.md")
        self.assertEqual(saved.json()["current_version"]["source"], "markdown_edit")
        self.assertEqual(saved.json()["current_version"]["note"], "Clarify")

        stale = self.post_file(b"# Competing draft", url=endpoint, base_version=original_version)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(Version.objects.filter(document_id=original["id"]).count(), 2)
        self.assertEqual((self.storage / Version.objects.get(pk=original_version).path).read_bytes(), b"# Original")

    def test_html_rejects_markdown_editor_endpoint(self):
        original = self.post_file(b"<p>HTML</p>", "example.html").json()
        response = self.post_file(
            b"<p>Updated</p>", "example.html",
            url=f"/api/documents/{original['id']}/markdown/",
            base_version=original["current_version"]["id"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Version.objects.filter(document_id=original["id"]).count(), 1)

    def test_reader_download_matches_the_displayed_version(self):
        created = self.post_file(b"# First version").json()
        endpoint = f"/api/documents/{created['id']}/"
        latest = self.post_file(b"# Second version", url=endpoint + "versions/").json()
        self.client.force_login(self.viewer)

        expired = self.client.get(endpoint + "download/", {"version": created["current_version"]["id"]})
        self.assertEqual(expired.status_code, 409)
        response = self.client.get(endpoint + "download/", {"version": latest["current_version"]["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"# Second version")

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
