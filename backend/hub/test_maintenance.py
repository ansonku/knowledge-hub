import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from documents.models import DocumentImage, PendingDocumentDeletion, Version
from documents.test_images import picture
from users.models import AuditLog, User

from . import maintenance

URL = "/api/admin/system/maintenance/"


class MaintenanceTests(TransactionTestCase):
    """P7d: Admins run the start-up maintenance steps from the system status page."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage))
        settings.enable()
        self.addCleanup(settings.disable)
        cache.clear()
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN, display_name="管理員")
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(self.admin)
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("doc.md", b"# doc\n")})
        self.assertEqual(response.status_code, 201, response.content)
        self.doc = response.json()["id"]

    def run_maintenance(self, client=None):
        return (client or self.client).post(URL)

    def results(self):
        response = self.run_maintenance()
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def test_only_admins_can_run_it(self):
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(self.run_maintenance(editor).status_code, 403)
        self.assertEqual(self.run_maintenance(Client()).status_code, 403)
        self.assertEqual(Client().get(URL).status_code, 403)
        self.assertEqual(self.client.get(URL).status_code, 405)
        self.assertFalse(AuditLog.objects.filter(action=maintenance.ACTION).exists())

    def test_a_clean_store_reports_nothing_to_do(self):
        self.assertEqual(self.results(), {
            "deletions": {"done": 0, "failed": 0},
            "index": {"indexed": 0, "failed": 0},
            "images": {"removed": 0, "bytes": 0},
            "storage": {"checked": 1, "missing": 0, "unreferenced": 0},
        })

    def test_it_does_the_pending_work(self):
        # An unused image past the grace period.
        image = self.client.post(f"/api/documents/{self.doc}/images/", {"file": SimpleUploadedFile("a.png", picture())}).json()
        DocumentImage.objects.filter(pk=image["id"]).update(uploaded_at=timezone.now() - timedelta(hours=30))
        # A current version without search text.
        Version.objects.filter(document_id=self.doc).update(search_text=None)
        # Files of a permanently deleted document still on disk.
        leftover = self.storage / "versions" / "11111111-1111-1111-1111-111111111111"
        leftover.mkdir(parents=True)
        (leftover / "v").write_bytes(b"old")
        PendingDocumentDeletion.objects.create(document_id="11111111-1111-1111-1111-111111111111")
        results = self.results()
        self.assertEqual(results["deletions"], {"done": 1, "failed": 0})
        self.assertEqual(results["index"], {"indexed": 1, "failed": 0})
        self.assertEqual(results["images"], {"removed": 1, "bytes": image["size"]})
        self.assertFalse(leftover.exists())
        self.assertTrue(Version.objects.get(document_id=self.doc).search_text)

    def test_storage_check_counts_but_never_moves_or_names_files(self):
        stray = self.storage / "versions" / self.doc / "stray"
        stray.write_bytes(b"x")
        version = Version.objects.get(document_id=self.doc)
        (self.storage / version.path).unlink()
        response = self.run_maintenance()
        self.assertEqual(response.json()["results"]["storage"], {"checked": 1, "missing": 1, "unreferenced": 1})
        self.assertTrue(stray.exists())
        self.assertNotIn(str(self.storage), response.content.decode())
        self.assertNotIn("versions/", response.content.decode())
        report = self.client.get("/api/admin/system/").json()
        self.assertIn("missing_files", {note["key"] for note in report["warnings"]})
        self.assertNotIn("versions/", str(report))

    def test_runs_are_audited_and_shown_on_the_status_page(self):
        self.assertIsNone(self.client.get("/api/admin/system/").json()["maintenance"])
        results = self.results()
        entry = AuditLog.objects.get(action=maintenance.ACTION)
        self.assertEqual((entry.actor, entry.target), (self.admin, self.admin))
        self.assertEqual(entry.metadata, {"maintenance": results})
        last = self.client.get("/api/admin/system/").json()["maintenance"]
        self.assertEqual((last["actor"], last["results"]), ("管理員", results))
        row = next(row for row in self.client.get("/api/admin/audit/").json()["results"] if row["action"] == maintenance.ACTION)
        self.assertEqual(row["detail"], {"maintenance": results})

    def test_one_run_at_a_time(self):
        cache.add(maintenance.LOCK, 0, 60)
        response = self.run_maintenance()
        self.assertEqual(response.status_code, 409)
        self.assertIn("正在執行", response.json()["detail"])
        cache.delete(maintenance.LOCK)
        self.assertEqual(self.run_maintenance().status_code, 200)
        # The lock is released after a run, even a failing one.
        self.assertTrue(cache.add(maintenance.LOCK, 0, 60))

    def test_a_failing_step_never_stops_the_others(self):
        def broken():
            raise OSError("disk")

        steps = (("deletions", broken), *maintenance.STEPS[1:])
        with patch.object(maintenance, "STEPS", steps), self.assertLogs("hub.maintenance", "ERROR"):
            results = self.results()
        self.assertEqual(results["deletions"], {"error": True})
        self.assertEqual(results["storage"]["missing"], 0)
        self.assertTrue(cache.add(maintenance.LOCK, 0, 60))
