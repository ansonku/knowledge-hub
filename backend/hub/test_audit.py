import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from documents.models import Document
from users.lifecycle import audit
from users.models import AuditLog, User


class AuditFeedTests(TransactionTestCase):
    """P4d: the Admin audit trail merges account, document and deletion records."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN, display_name="Ada")
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.admin)

    def as_user(self, user):
        client = Client()
        client.force_login(user)
        return client

    def upload(self, client, content, title):
        response = client.post("/api/documents/", {"file": SimpleUploadedFile("doc.md", content), "title": title})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def feed(self, **params):
        response = self.client.get("/api/admin/audit/", params)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()

    def test_only_admins_can_read(self):
        self.assertEqual(Client().get("/api/admin/audit/").status_code, 403)
        for user in (self.viewer, self.editor):
            self.assertEqual(self.as_user(user).get("/api/admin/audit/").status_code, 403)

    def test_merges_sources_in_time_order_with_whitelisted_details(self):
        editor = self.as_user(self.editor)
        kept = self.upload(editor, b"kept", "Kept doc")
        gone = self.upload(editor, b"gone", "Gone doc")
        audit("mfa_admin_reset", self.viewer, self.admin, reason="Desk check", identity_verified=True, secret="never")
        audit("login", self.viewer, self.viewer)
        editor.delete(f"/api/documents/{gone}/")
        response = self.client.post(f"/api/trash/{gone}/delete/", {"title": "Gone doc", "confirm": True},
                                    content_type="application/json")
        self.assertIn(response.status_code, (202, 204), response.content)

        rows = self.feed()["results"]
        stamps = [row["created_at"] for row in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        by_action = {(row["category"], row["action"]): row for row in rows}
        reset = by_action[("account", "mfa_admin_reset")]
        self.assertEqual(reset["actor"], {"id": str(self.admin.pk), "name": "Ada"})
        self.assertEqual(reset["member"]["id"], str(self.viewer.pk))
        self.assertEqual(reset["detail"], {"reason": "Desk check", "identity_verified": True})
        self.assertIn(("signin", "login"), by_action)
        created = next(row for row in rows if row["action"] == "created" and row["document"]["id"] == kept)
        self.assertEqual(created["document"], {"id": kept, "title": "Kept doc", "deleted": False})
        self.assertEqual(created["version_number"], 1)
        deletion = by_action[("deletion", "permanent")]
        self.assertEqual(deletion["document"], {"id": gone, "title": "Gone doc", "deleted": True})
        self.assertEqual(deletion["detail"], {"version_count": 1})
        self.assertEqual(deletion["actor"]["id"], str(self.admin.pk))
        # The permanently deleted document's own activity went with it.
        self.assertFalse(Document.objects.filter(pk=gone).exists())
        self.assertNotIn("never", str(rows))

    def test_filters_and_paging(self):
        editor = self.as_user(self.editor)
        document = self.upload(editor, b"one", "One")
        editor.delete(f"/api/documents/{document}/")
        audit("role_changed", self.viewer, self.admin, old_role="viewer", role="editor")
        audit("login", self.editor, self.editor)

        def actions(**params):
            return sorted({(row["category"], row["action"]) for row in self.feed(**params)["results"]})

        self.assertEqual(actions(category="trash"), [("trash", "trashed")])
        self.assertEqual(actions(category="document"), [("document", "created")])
        self.assertEqual(actions(category="signin"), [("signin", "login")])
        self.assertEqual(actions(category="account"), [("account", "role_changed")])
        self.assertEqual(actions(actor=str(self.editor.pk)),
                         [("document", "created"), ("signin", "login"), ("trash", "trashed")])
        self.assertEqual(actions(member=str(self.viewer.pk)), [("account", "role_changed")])
        self.assertNotIn(("signin", "login"), actions(signins="false"))
        self.assertIn(("signin", "login"), actions())
        self.assertEqual(actions(category="signin", signins="false"), [("signin", "login")])
        later = (timezone.now() + timedelta(minutes=1)).isoformat()
        self.assertEqual(self.feed(since=later)["results"], [])
        self.assertEqual(self.feed(until=later)["results"], self.feed()["results"])
        self.assertEqual(self.client.get("/api/admin/audit/", {"category": "nope"}).status_code, 400)
        self.assertEqual(self.client.get("/api/admin/audit/", {"actor": "nope"}).status_code, 400)

        AuditLog.objects.bulk_create([AuditLog(target=self.viewer, actor=self.admin, action="enabled") for _ in range(55)])
        first, second = self.feed(category="account"), self.feed(category="account", page=2)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(first["results"]), 50)
        self.assertFalse(second["has_more"])
        self.assertEqual(len(second["results"]), 6)
        self.assertFalse({row["id"] for row in first["results"]} & {row["id"] for row in second["results"]})
