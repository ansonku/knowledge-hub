import json
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from documents.models import PendingDocumentDeletion, Version
from users.models import User


class SystemStatusTests(TransactionTestCase):
    """P4e: the Admin system status report."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage), EMAIL_HOST="", MFA_ENCRYPTION_KEY=None)
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        User.objects.create_user("invitee", "invitee@example.test", is_active=False, pending_activation=True)
        self.client.force_login(self.admin)

    def report(self):
        response = self.client.get("/api/admin/system/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()

    def test_only_admins(self):
        self.assertEqual(Client().get("/api/admin/system/").status_code, 403)
        for user in (self.viewer, self.editor):
            client = Client()
            client.force_login(user)
            self.assertEqual(client.get("/api/admin/system/").status_code, 403)

    def test_counts_jobs_flags_and_no_paths_or_secrets(self):
        editor = Client()
        editor.force_login(self.editor)
        ids = [editor.post("/api/documents/", {"file": SimpleUploadedFile("a.md", content)}).json()["id"]
               for content in (b"first", b"second!")]
        editor.delete(f"/api/documents/{ids[1]}/")
        Version.objects.filter(document_id=ids[0]).update(search_text=None)
        PendingDocumentDeletion.objects.create(document_id=ids[1])

        report = self.report()
        self.assertEqual(report["content"] | {}, {"documents": 1, "trashed": 1, "versions": 2, "published": 0,
                                                 "collections": 0, "tags": 0, "images": 0})
        self.assertEqual(report["storage"]["versions_bytes"], len(b"first") + len(b"second!"))
        self.assertGreater(report["storage"]["database_bytes"], 0)
        self.assertGreater(report["storage"]["disk"]["total_bytes"], 0)
        self.assertEqual(report["members"] | {}, {
            "total": 4, "active": 3, "pending": 1, "disabled": 0,
            "by_role": {"admin": 1, "editor": 1, "viewer": 2}, "active_admins": 1, "mfa_enabled": 0,
        })
        self.assertEqual(report["jobs"]["pending_deletions"], 1)
        self.assertIsNotNone(report["jobs"]["oldest_pending_deletion"])
        self.assertEqual(report["jobs"]["unindexed_documents"], 1)
        self.assertEqual(report["config"]["smtp"], False)
        self.assertEqual(report["config"]["https"], False)
        keys = {note["key"] for note in report["warnings"]}
        self.assertEqual(keys, {"pending_deletions", "unindexed", "single_admin", "smtp"})
        dumped = json.dumps(report)
        for leak in (str(self.storage), "SECRET", "secret", "/var/lib", "@example.test"):
            self.assertNotIn(leak, dumped)

    def test_https_without_mfa_key_is_flagged(self):
        with override_settings(PUBLIC_ORIGIN="https://hub.example.test", EMAIL_HOST="smtp.example.test"):
            keys = {note["key"] for note in self.report()["warnings"]}
        self.assertIn("mfa_key", keys)
        self.assertNotIn("smtp", keys)
