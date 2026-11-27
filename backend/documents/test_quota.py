"""P23: the storage limit — usage, refused uploads, the admin API and system warnings."""
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from users.models import AuditLog

from . import limits, quota
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
        self.assertEqual(set(response.json()), {"file"})  # nothing else would be shown
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


class FileLimitTests(ImageFixture):
    """P23c: per-file limits set by admins, separately for Markdown, HTML, images and videos."""

    def set_limits(self, **values):
        return self.as_user(self.admin).put("/api/admin/storage/", {"file_limits": values}, content_type="application/json")

    def test_defaults_match_the_old_limits(self):
        found = self.as_user(self.admin).get("/api/admin/storage/").json()["file_limits"]
        self.assertEqual({kind: (row["mb"], row["min"], row["max"]) for kind, row in found.items()}, {
            "markdown": (50, 1, 50), "html": (50, 1, 100), "image": (10, 1, 30), "video": (200, 10, 1024),
        })
        members = self.client.get("/api/auth/me").json()["limits"]
        self.assertEqual(members["markdown_bytes"], 50 * limits.MB)
        self.assertEqual(members["video_bytes"], 200 * limits.MB)

    def test_markdown_and_html_have_their_own_limits(self):
        self.assertEqual(self.set_limits(markdown=1, html=2).status_code, 200)
        with patch("documents.limits.MB", 100):  # 1 "MB" = 100 bytes
            big_md = self.client.post("/api/documents/", {"file": SimpleUploadedFile("a.md", b"#" * 150)})
            self.assertEqual(big_md.status_code, 400)
            self.assertEqual(big_md.json()["file"], "Markdown 文件超過上限 1 MB。")
            html = self.client.post("/api/documents/", {"file": SimpleUploadedFile("a.html", b"<p>" + b"x" * 150)})
            self.assertEqual(html.status_code, 201, html.content)  # 153 bytes is within the HTML limit (200)
            too_big = self.client.post(f"/api/documents/{html.json()['id']}/versions/", {"file": SimpleUploadedFile("a.html", b"<p>" + b"x" * 250)})
            self.assertEqual(too_big.json()["file"], "HTML 文件超過上限 2 MB。")
        members = self.client.get("/api/auth/me").json()["limits"]
        self.assertEqual((members["markdown_bytes"], members["html_bytes"]), (limits.MB, 2 * limits.MB))

    def test_image_limit(self):
        self.set_limits(image=1)
        with patch("documents.limits.MB", 100):
            response = self.upload(picture(size=(200, 200)))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["file"], "圖片超過上限 1 MB。")

    def test_restoring_an_old_version_is_not_limited(self):
        big = self.edit("# 文件\n\n" + "內容" * 100)  # about 600 bytes
        self.edit("# 短\n")
        self.set_limits(markdown=1)
        with patch("documents.limits.MB", 10):  # the limit is now 10 bytes; restoring keeps the old version's size
            response = self.client.post(f"/api/documents/{self.doc}/versions/{big}/restore/",
                                        {"base_version": self.current()}, content_type="application/json")
        self.assertIn(response.status_code, (200, 201), response.content)

    def test_ranges_admins_and_audit(self):
        admin = self.as_user(self.admin)
        for values in ({"markdown": 0}, {"markdown": 51}, {"html": 101}, {"image": 31}, {"video": 9}, {"video": 1025}):
            self.assertEqual(self.set_limits(**values).status_code, 400, values)
        self.assertEqual(admin.put("/api/admin/storage/", {}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.put("/api/admin/storage/", {"file_limits": {"image": 5}}, content_type="application/json").status_code, 403)
        response = self.set_limits(video=1024, image=10)  # image 10 is the default: nothing to record for it
        self.assertEqual(response.json()["file_limits"]["video"]["mb"], 1024)
        row = AuditLog.objects.get(action="file_limits_updated")
        self.assertEqual(row.metadata["limits"], {"video": {"from": 200, "to": 1024}})
        self.set_limits(video=None)
        self.assertEqual(SiteSettings.current().video_max_mb, None)
        self.assertEqual(admin.get("/api/admin/storage/").json()["file_limits"]["video"]["mb"], 200)
