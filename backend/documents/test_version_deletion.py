import importlib
import tempfile
from pathlib import Path

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import DocumentActivity, DocumentImage, Version, VersionImage, VersionRestoreAudit
from .test_images import picture


class VersionDeletionTests(TransactionTestCase):
    """P8b: Admins permanently delete single versions; current and published versions stay."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN, display_name="管理員")
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(self.admin)
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("doc.md", b"# v1\n")})
        self.doc = response.json()["id"]
        for text in ("# v2\n", "# v3\n"):
            self.edit(text)

    def versions(self):
        return {version.number: version for version in Version.objects.filter(document_id=self.doc)}

    def current(self):
        return self.client.get(f"/api/documents/{self.doc}/").json()["current_version"]["id"]

    def edit(self, text):
        response = self.client.post(f"/api/documents/{self.doc}/markdown/", {
            "file": SimpleUploadedFile("doc.md", text.encode()), "base_version": self.current(),
        })
        self.assertEqual(response.status_code, 201, response.content)

    def delete(self, number, client=None, sent=None, reason=""):
        version = self.versions()[number]
        return (client or self.client).post(
            f"/api/documents/{self.doc}/versions/{version.pk}/delete/",
            {"number": number if sent is None else sent, "reason": reason}, content_type="application/json",
        )

    def test_admin_deletes_an_old_version_and_its_file(self):
        v2 = self.versions()[2]
        path = self.storage / v2.path
        self.assertTrue(path.exists())
        response = self.delete(2, reason="上傳錯檔案")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertNotIn(2, self.versions())
        self.assertFalse(path.exists())
        entry = DocumentActivity.objects.get(document_id=self.doc, action=DocumentActivity.Action.VERSION_DELETED)
        self.assertEqual((entry.actor, entry.version_number, entry.detail), (self.admin, 2, {"reason": "上傳錯檔案"}))

    def test_only_admins(self):
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(self.delete(1, editor).status_code, 403)
        self.assertEqual(self.delete(1, Client()).status_code, 403)
        self.assertIn(1, self.versions())

    def test_the_typed_number_must_match(self):
        response = self.delete(1, sent=2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("v1", str(response.json()))
        self.assertIn(1, self.versions())

    def test_current_and_published_versions_stay(self):
        response = self.delete(3)
        self.assertEqual(response.status_code, 400)
        self.assertIn("目前版本", str(response.json()))
        v2 = self.versions()[2]
        published = self.client.post(f"/api/documents/{self.doc}/publication/", {"version": str(v2.pk), "title": "doc"},
                                     content_type="application/json")
        self.assertEqual(published.status_code, 200, published.content)
        response = self.delete(2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("公開中", str(response.json()))
        self.assertIn(2, self.versions())

    def test_trashed_documents_versions_stay(self):
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.delete(1).status_code, 404)

    def test_a_version_of_another_document_is_404(self):
        other = self.client.post("/api/documents/", {"file": SimpleUploadedFile("o.md", b"# other\n")}).json()["id"]
        v1 = self.versions()[1]
        response = self.client.post(f"/api/documents/{other}/versions/{v1.pk}/delete/", {"number": 1}, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_restore_history_survives_deleting_the_source(self):
        v1 = self.versions()[1]
        response = self.client.post(f"/api/documents/{self.doc}/versions/{v1.pk}/restore/", {"base_version": self.current()},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.delete(1).status_code, 204)
        v4 = self.versions()[4]
        self.assertEqual((v4.restored_from_id, v4.restored_from_number), (None, 1))
        detail = self.client.get(f"/api/documents/{self.doc}/").json()["current_version"]
        self.assertEqual(detail["restored_from_number"], 1)
        audit = VersionRestoreAudit.objects.get(document_id=self.doc)
        self.assertEqual((audit.restored_from_id, audit.restored_from_number, audit.previous_number, audit.new_number), (None, 1, 3, 4))
        # The previous version of a restore can go too; the audit keeps its numbers.
        self.assertEqual(self.delete(3).status_code, 204)
        self.assertEqual(VersionRestoreAudit.objects.get(document_id=self.doc).previous_number, 3)

    def test_history_lists_where_deleted_versions_were(self):
        self.delete(1, reason="測試")
        history = self.client.get(f"/api/documents/{self.doc}/versions/").json()
        self.assertEqual([version["number"] for version in history["results"]], [3, 2])
        self.assertEqual(len(history["deleted"]), 1)
        self.assertEqual({key: history["deleted"][0][key] for key in ("number", "deleted_by", "reason")},
                         {"number": 1, "deleted_by": "管理員", "reason": "測試"})

    def test_deleted_versions_are_gone_from_detail_and_download(self):
        v1 = self.versions()[1]
        self.delete(1)
        self.assertEqual(self.client.get(f"/api/documents/{self.doc}/versions/{v1.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{self.doc}/versions/{v1.pk}/download/").status_code, 404)

    def test_image_references_go_with_the_version(self):
        image = self.client.post(f"/api/documents/{self.doc}/images/", {"file": SimpleUploadedFile("a.png", picture())}).json()
        self.edit(f"![a](/api/images/{image['id']}/)\n")  # v4
        self.edit("沒有圖片\n")  # v5
        self.assertEqual(self.delete(4).status_code, 204)
        self.assertFalse(VersionImage.objects.filter(image_id=image["id"]).exists())
        self.assertTrue(DocumentImage.objects.filter(pk=image["id"]).exists())  # removed later by the 24-hour cleanup

    def test_audit_feed_lists_it_under_deletions(self):
        self.delete(2, reason="原因")
        rows = self.client.get("/api/admin/audit/", {"category": "deletion"}).json()["results"]
        row = next(row for row in rows if row["action"] == "version_deleted")
        self.assertEqual((row["category"], row["version_number"], row["detail"]), ("deletion", 2, {"reason": "原因"}))
        documents = self.client.get("/api/admin/audit/", {"category": "document"}).json()["results"]
        self.assertFalse(any(row["action"] == "version_deleted" for row in documents))

    def test_permanently_deleting_the_document_still_works(self):
        self.delete(1)
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        response = self.client.post(f"/api/trash/{self.doc}/delete/", {"title": "doc", "confirm": True}, content_type="application/json")
        self.assertIn(response.status_code, (200, 204), response.content)
        self.assertFalse(Version.objects.filter(document_id=self.doc).exists())

    def test_migration_backfills_numbers_of_existing_restores(self):
        v1 = self.versions()[1]
        self.client.post(f"/api/documents/{self.doc}/versions/{v1.pk}/restore/", {"base_version": self.current()},
                         content_type="application/json")
        Version.objects.update(restored_from_number=None)
        VersionRestoreAudit.objects.update(restored_from_number=None, previous_number=None, new_number=None)
        backfill = importlib.import_module("documents.migrations.0015_deletable_versions").backfill_numbers
        backfill(apps, None)
        self.assertEqual(self.versions()[4].restored_from_number, 1)
        audit = VersionRestoreAudit.objects.get()
        self.assertEqual((audit.restored_from_number, audit.previous_number, audit.new_number), (1, 3, 4))
