import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier
from uuid import UUID
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connections
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from users.models import User

from .models import Document, DocumentTrashAudit, PendingDocumentDeletion, PreviewTicket, Version, VersionRestoreAudit
from .services import VersionConflict, add_upload, restore_version


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

    def test_history_download_and_restore_preserve_originals_and_record_audit(self):
        created = self.post_file(b"# Before", "article.md").json()
        document_id = created["id"]
        endpoint = f"/api/documents/{document_id}/versions/"
        current = self.post_file(b"# After", "updated.md", endpoint).json()["current_version"]
        original = created["current_version"]
        restore_url = f"{endpoint}{original['id']}/restore/"
        request = {"base_version": current["id"], "note": "Restore reviewed text"}

        viewer = Client()
        viewer.force_login(self.viewer)
        listing = viewer.get(endpoint).json()
        self.assertEqual(listing["current"], current["id"])
        self.assertEqual([entry["number"] for entry in listing["results"]], [2, 1])
        self.assertEqual(listing["results"][1]["author"], self.editor.username)
        self.assertEqual(viewer.get(f"{endpoint}{original['id']}/").json()["number"], 1)
        old_download = viewer.get(f"{endpoint}{original['id']}/download/")
        self.assertIn("article.md", old_download["Content-Disposition"])
        self.assertEqual(b"".join(old_download.streaming_content), b"# Before")
        self.assertEqual(Client().get(endpoint).status_code, 403)
        self.assertEqual(viewer.post(restore_url, request, content_type="application/json").status_code, 403)

        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.editor)
        self.assertEqual(browser.post(restore_url, request, content_type="application/json").status_code, 403)
        token = browser.get("/api/auth/me").json()["csrf_token"]
        response = browser.post(restore_url, request, content_type="application/json", headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 201, response.content)
        new = response.json()["current_version"]
        self.assertEqual(new["number"], 3)
        self.assertEqual(new["note"], request["note"])
        self.assertEqual(new["source"], "restore")
        self.assertEqual(new["restored_from"], original["id"])
        restored, original_row = Version.objects.get(pk=new["id"]), Version.objects.get(pk=original["id"])
        self.assertNotEqual(restored.path, original_row.path)
        self.assertEqual(new["sha256"], original["sha256"])
        self.assertEqual(original_row.sha256, original["sha256"])
        self.assertEqual((self.storage / original_row.path).read_bytes(), b"# Before")
        self.assertEqual((self.storage / restored.path).read_bytes(), b"# Before")
        audit = VersionRestoreAudit.objects.get(new_version_id=new["id"])
        self.assertEqual(str(audit.previous_version_id), current["id"])
        self.assertEqual(str(audit.restored_from_id), original["id"])
        self.assertEqual(audit.actor_id, self.editor.pk)
        self.assertEqual(self.client.post(restore_url, request, content_type="application/json").status_code, 409)

    @override_settings(LOCAL_HTML_PREVIEW=True, PUBLIC_ORIGIN="http://localhost:18080")
    def test_history_is_scoped_to_document_and_historical_preview_keeps_the_sandbox(self):
        first = self.post_file(b"<p>First</p>", "example.html").json()
        second = self.post_file(b"<p>Other</p>", "other.html").json()
        original = first["current_version"]["id"]
        endpoint = f"/api/documents/{first['id']}/versions/"
        update = self.post_file(b"<p>Latest</p>", "example.html", endpoint)
        self.assertEqual(update.status_code, 201)
        viewer = Client()
        viewer.force_login(self.viewer)
        for action in ("", "download/"):
            path = f"/api/documents/{second['id']}/versions/{original}/{action}"
            self.assertEqual(viewer.get(path).status_code, 404)
        ticket = viewer.post(f"{endpoint}{original}/preview/", {}, content_type="application/json", HTTP_HOST="localhost")
        self.assertEqual(ticket.status_code, 201, ticket.content)
        preview = Client().get(ticket.json()["url"], HTTP_HOST="localhost")
        self.assertEqual(b"".join(preview.streaming_content), b"<p>First</p>")
        self.assertIn("sandbox allow-scripts", preview["Content-Security-Policy"])
        self.assertEqual(Client().get(ticket.json()["url"], HTTP_HOST="localhost").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/documents/{first['id']}/").status_code, 204)
        self.assertEqual(viewer.get(f"{endpoint}{original}/download/").status_code, 404)

    def test_concurrent_restores_with_same_base_accept_only_one(self):
        first = self.post_file(b"# Old version").json()
        document_id = UUID(first["id"])
        target = UUID(first["current_version"]["id"])
        result = self.post_file(b"# New version", url=f"/api/documents/{document_id}/versions/").json()
        base = UUID(result["current_version"]["id"])
        barrier = Barrier(2)

        def restore_simultaneously(_):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                try:
                    return restore_version(self.editor, document_id, target, base_version=base).current_version.number
                except VersionConflict:
                    return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(set(executor.map(restore_simultaneously, range(2), timeout=10)), {3, "conflict"})
        self.assertEqual(VersionRestoreAudit.objects.filter(document_id=document_id).count(), 1)

    def test_search_chinese_body_metadata_and_current_version_only(self):
        markdown = self.post_file("專案正在進行開機驗證，全程留存紀錄。".encode(), title="Firmware guide").json()
        html = self.post_file(
            "<script>只在脚本出現</script><style>.樣式暗碼{color:red}</style><p>雙語<strong>部署指南</strong></p>".encode(),
            "example.html", title="Deployment notes",
        ).json()
        category = self.client.post("/api/categories/", {"name": "韌體工程"}, content_type="application/json").json()["id"]
        tag = self.client.post("/api/tags/", {"name": "啟動流程"}, content_type="application/json").json()["id"]
        self.client.patch(f"/api/documents/{markdown['id']}/", {"category": category, "tags": [tag]}, content_type="application/json")
        viewer = Client()
        viewer.force_login(self.viewer)

        def result_ids(q):
            response = viewer.get("/api/documents/", {"q": q})
            self.assertEqual(response.status_code, 200, response.content)
            return [item["id"] for item in response.json()["results"]]

        self.assertEqual(result_ids("開機驗證"), [markdown["id"]])
        self.assertEqual(result_ids("雙語部署"), [html["id"]])
        self.assertEqual(result_ids("Deployment"), [html["id"]])
        self.assertEqual(result_ids("韌體工程 啟動流程"), [markdown["id"]])
        self.assertEqual(result_ids("只在脚本出現"), [])
        self.assertEqual(result_ids("樣式暗碼"), [])
        self.assertEqual(Client().get("/api/documents/", {"q": "開機驗證"}).status_code, 403)

        version_path = f"/api/documents/{markdown['id']}/versions/"
        self.assertEqual(self.post_file("改用新的回歸測試流程。".encode(), url=version_path).status_code, 201)
        self.assertEqual(result_ids("開機驗證"), [])
        self.assertEqual(result_ids("回歸測試"), [markdown["id"]])
        self.client.delete(f"/api/documents/{markdown['id']}/")
        self.assertEqual(result_ids("回歸測試"), [])

    def test_existing_version_search_backfill_uses_original_file(self):
        item = self.post_file("校正舊資料全文索引".encode()).json()
        current = Version.objects.get(pk=item["current_version"]["id"])
        Version.objects.filter(pk=current.pk).update(search_text=None)
        self.assertEqual(self.client.get("/api/documents/", {"q": "全文索引"}).json()["count"], 0)
        call_command("index_document_search")
        self.assertEqual(self.client.get("/api/documents/", {"q": "全文索引"}).json()["count"], 1)
        self.assertEqual((self.storage / current.path).read_bytes(), "校正舊資料全文索引".encode())

    def test_trash_restore_and_admin_permanent_delete(self):
        original = self.post_file(b"# Start", title="Document to remove").json()
        document_id = original["id"]
        url = f"/api/documents/{document_id}/"
        trash_url = f"/api/trash/{document_id}/"
        v2 = self.post_file(b"# Next", url=url + "versions/").json()["current_version"]
        v1 = original["current_version"]
        self.client.post(url + f"versions/{v1['id']}/restore/", {"base_version": v2["id"]}, content_type="application/json")
        stored = list(Version.objects.filter(document_id=document_id).values_list("path", flat=True))
        self.assertEqual(len(stored), 3)
        admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get("/api/trash/").json()["results"][0]["version_count"], 3)
        self.assertEqual(self.client.get(url + "download/").status_code, 404)
        self.assertEqual(self.client.post(trash_url + "restore/").status_code, 200)
        self.assertTrue(all((self.storage / path).exists() for path in stored))
        self.assertEqual(self.client.get(url + "versions/").json()["count"], 3)
        self.assertEqual(self.client.delete(url).status_code, 204)
        request = {"title": original["title"], "confirm": True}
        self.assertEqual(self.client.post(trash_url + "delete/", request, content_type="application/json").status_code, 403)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get("/api/trash/").status_code, 403)
        self.assertEqual(self.client.post(trash_url + "restore/").status_code, 403)
        self.client.force_login(admin)
        for changes in ({"confirm": False}, {"title": "wrong"}):
            self.assertEqual(self.client.post(trash_url + "delete/", request | changes, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(trash_url + "delete/", request, content_type="application/json").status_code, 204)
        self.assertFalse(Document.objects.filter(pk=document_id).exists())
        self.assertFalse(Version.objects.filter(document_id=document_id).exists())
        self.assertTrue(all(not (self.storage / path).exists() for path in stored))
        self.assertFalse(PendingDocumentDeletion.objects.exists())
        audit = DocumentTrashAudit.objects.get(document_id=document_id, action="permanent")
        self.assertEqual((audit.actor_id, audit.version_count), (admin.pk, 3))

    def test_permanent_file_cleanup_can_be_retried(self):
        item = self.post_file(b"# Retry cleanup").json()
        document_id = item["id"]
        self.client.delete(f"/api/documents/{document_id}/")
        self.client.force_login(User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN))
        request = {"title": item["title"], "confirm": True}
        with patch("documents.trash.shutil.rmtree", side_effect=OSError("storage temporarily offline")):
            response = self.client.post(f"/api/trash/{document_id}/delete/", request, content_type="application/json")
        self.assertEqual(response.status_code, 202)
        self.assertFalse(Document.objects.filter(pk=document_id).exists())
        self.assertTrue(PendingDocumentDeletion.objects.filter(pk=document_id).exists())
        call_command("finish_document_deletions")
        self.assertFalse(PendingDocumentDeletion.objects.filter(pk=document_id).exists())
        self.assertFalse((self.storage / "versions" / document_id).exists())

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
