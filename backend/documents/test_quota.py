"""P23: the storage limit — usage, refused uploads, the admin API and system warnings."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from users.models import AuditLog

from . import quota
from .models import DocumentImage, SiteSettings, Version
from .test_images import ImageFixture, picture


def set_limit(value):
    SiteSettings.objects.update_or_create(pk=1, defaults={"storage_limit": value})


class StorageUsageTests(ImageFixture):
    def test_usage_counts_versions_old_versions_trash_and_media(self):
        image = self.uploaded(picture(size=(40, 30)))
        self.edit(f"# 文件\n\n![a]({image['url']})\n")
        trashed = self.create("# 回收\n" + "x" * 500, "trashed.md")
        self.assertEqual(self.client.delete(f"/api/documents/{trashed}/").status_code, 204)
        parts = quota.usage()["parts"]
        current = Version.objects.get(pk=self.current()).size
        self.assertEqual(parts["versions_current"], current)
        self.assertEqual(parts["versions_old"], Version.objects.filter(document_id=self.doc).exclude(pk=self.current()).get().size)
        self.assertEqual(parts["trash"], Version.objects.get(document_id=trashed).size)
        self.assertEqual(parts["images"], DocumentImage.objects.get(pk=image["id"]).size)
        self.assertGreater(parts["database"], 0)
        self.assertEqual(quota.usage()["total"], sum(parts.values()))

    def test_levels(self):
        self.assertIsNone(quota.level(10, None))
        self.assertIsNone(quota.level(79, 100))
        self.assertEqual(quota.level(80, 100), "notice")
        self.assertEqual(quota.level(90, 100), "warning")
        self.assertEqual(quota.level(100, 100), "full")


class StorageLimitTests(ImageFixture):
    def fill_up(self):
        set_limit(quota.usage()["total"] + 10)

    def test_uploads_past_the_limit_are_refused(self):
        self.fill_up()
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("新.md", b"# new\n" + b"x" * 200)})
        self.assertEqual(response.status_code, 413)
        self.assertIn("儲存空間已達上限", response.json()["file"])
        self.assertIn("請聯絡管理員", response.json()["file"])
        response = self.client.post(f"/api/documents/{self.doc}/versions/", {"file": SimpleUploadedFile("doc.md", b"# v2\n" + b"y" * 200)})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.upload(picture(size=(40, 30))).status_code, 413)

    def test_markdown_text_saves_are_not_limited(self):
        self.fill_up()
        self.edit("# 文件\n\n" + "內容" * 200)

    def test_no_limit_means_no_check(self):
        set_limit(None)
        self.uploaded(picture(size=(40, 30)))

    def test_every_upload_keeps_the_disk_free(self):
        with override_settings(UPLOAD_MIN_FREE_BYTES=10 ** 18), self.assertLogs("documents.quota", "ERROR"):
            response = self.upload(picture())
        self.assertEqual(response.status_code, 413)
        self.assertIn("磁碟空間不足", response.json()["file"])
        with override_settings(UPLOAD_MIN_FREE_BYTES=10 ** 18), self.assertLogs("documents.quota", "ERROR"):
            response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("新.md", b"# new\n")})
        self.assertEqual(response.status_code, 413)


class StorageSettingsTests(ImageFixture):
    def test_admins_read_and_set_the_limit_with_an_audit_row(self):
        admin = self.as_user(self.admin)
        found = admin.get("/api/admin/storage/").json()
        self.assertIsNone(found["limit"])
        self.assertEqual(set(found["parts"]), {"database", "versions_current", "versions_old", "images", "videos", "trash"})
        self.assertIsNone(found["level"])
        response = admin.put("/api/admin/storage/", {"limit": 100 * quota.GB}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["limit"], 100 * quota.GB)
        row = AuditLog.objects.get(action="storage_limit_updated")
        self.assertEqual(row.metadata["limit"], {"from": None, "to": 100 * quota.GB})
        self.assertEqual(admin.put("/api/admin/storage/", {"limit": None}, content_type="application/json").json()["limit"], None)

    def test_the_limit_is_at_least_one_gigabyte_and_admins_only(self):
        admin = self.as_user(self.admin)
        self.assertEqual(admin.put("/api/admin/storage/", {"limit": quota.GB - 1}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get("/api/admin/storage/").status_code, 403)
        self.assertEqual(self.client.put("/api/admin/storage/", {"limit": None}, content_type="application/json").status_code, 403)

    def test_system_status_warns_near_and_at_the_limit(self):
        admin = self.as_user(self.admin)
        used = quota.usage()["total"]
        for limit, level, text in ((int(used / 0.85), "warning", "80%"), (int(used / 0.95), "danger", "90%"), (used, "danger", "已達上限")):
            set_limit(limit)
            notes = {note["key"]: note for note in admin.get("/api/admin/system/").json()["warnings"]}
            self.assertEqual(notes["storage_limit"]["level"], level)
            self.assertIn(text, notes["storage_limit"]["text"])
        set_limit(None)
        self.assertNotIn("storage_limit", {note["key"] for note in admin.get("/api/admin/system/").json()["warnings"]})
