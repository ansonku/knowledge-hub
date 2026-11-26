"""P18: broken links in current versions, and media kept only by old versions."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from .models import DocumentVideo
from .test_images import ImageFixture, picture

MISSING = "99999999-9999-9999-9999-999999999999"


class BrokenLinkTests(ImageFixture):
    def setUp(self):
        super().setUp()
        self.ok = self.create("# 正常\n", "正常.md")
        self.trashed = self.create("# 已刪\n", "已刪.md")
        self.other = self.create("# 別份\n", "別份.md")
        self.gone = self.create("# 將刪的圖主\n", "圖主.md")
        self.own_image = self.uploaded()["url"]
        self.other_image = self.uploaded(picture(color=(1, 2, 3)), self.other)["url"]
        self.gone_image = self.uploaded(picture(color=(4, 5, 6)), self.gone)["url"]
        self.other_video = DocumentVideo.objects.create(document_id=self.other, sha256="0" * 64, format="mp4", size=10)
        self.assertEqual(self.client.delete(f"/api/documents/{self.trashed}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/documents/{self.gone}/").status_code, 204)

    def report(self, client=None):
        response = (client or self.client).get("/api/admin/broken-links/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def issues(self, document=None):
        rows = {row["id"]: row for row in self.report()["documents"]}
        return rows.get(document or self.doc, {"issues": []})["issues"]

    def test_finds_each_kind_with_lines_and_text(self):
        self.edit("\n".join([
            "# 文件",
            f"[正常的]({'/app/docs/' + self.ok + '/'})",
            f"[舊的](/app/docs/{self.trashed}/)",
            f"[不存在](/read/{MISSING}/)",
            "```",
            f"/app/docs/{MISSING}/ 程式碼裡的不算",
            "```",
            f"`/api/images/{MISSING}/` 行內程式碼也不算",
            f"![自己的圖]({self.own_image})",
            f"![別份的圖]({self.other_image})",
            f"![被清掉的圖](/api/images/{MISSING}/)",
            f"![回收桶的圖]({self.gone_image})",
            f"![別份的影片](/api/videos/{self.other_video.pk}/)",
        ]) + "\n")
        found = [(item["line"], item["kind"], item["severity"], item["text"]) for item in self.issues()]
        self.assertEqual(found, [
            (3, "document", "broken", "舊的"),
            (4, "document", "broken", "不存在"),
            (10, "image", "warning", "別份的圖"),
            (11, "image", "broken", "被清掉的圖"),
            (12, "image", "broken", "回收桶的圖"),
            (13, "video", "warning", "別份的影片"),
        ])
        trashed = self.issues()[0]
        self.assertIn("已刪", trashed["reason"])
        self.assertEqual(trashed["target_title"], "已刪")
        summary = self.report()["summary"]
        self.assertEqual((summary["broken"], summary["warnings"], summary["documents"]), (4, 2, 1))

    def test_only_current_versions_of_markdown_outside_the_trash(self):
        self.edit(f"[舊的](/app/docs/{self.trashed}/)\n")
        self.edit("已經修好了\n")
        self.assertEqual(self.issues(), [])
        source = self.create(f"另一份文件的[舊的](/app/docs/{self.trashed}/)\n", "來源.md")
        self.assertEqual(len(self.issues(source)), 1)
        self.client.delete(f"/api/documents/{source}/")
        self.assertEqual(self.issues(source), [])
        html = self.client.post("/api/documents/", {"file": SimpleUploadedFile("頁面.html", f'<a href="/app/docs/{MISSING}/">x</a>'.encode())})
        self.assertEqual(self.issues(html.json()["id"]), [])

    def test_public_article_linking_to_an_unpublished_document(self):
        version = self.edit(f"# 文件\n\n請看[正常的](/app/docs/{self.ok}/)\n")
        self.publish(version)
        warning = self.issues()[0]
        self.assertEqual((warning["kind"], warning["severity"], warning["line"], warning["published_version"]), ("public", "warning", 3, 2))
        published = self.as_user(self.admin).post(f"/api/documents/{self.ok}/publication/",
                                                  {"version": self.current(self.ok), "title": "正常"}, content_type="application/json")
        self.assertEqual(published.status_code, 200, published.content)
        self.assertEqual(self.issues(), [])

    def test_editors_and_admins_only(self):
        self.assertEqual(self.as_user(self.viewer).get("/api/admin/broken-links/").status_code, 403)
        self.assertEqual(self.as_user().get("/api/admin/broken-links/").status_code, 403)
        self.report(self.as_user(self.admin))

    def test_command_fails_on_broken_links(self):
        self.edit(f"[不存在](/app/docs/{MISSING}/)\n")
        with self.assertRaises(SystemExit) as raised:
            call_command("check_links", stdout=open("/dev/null", "w"))
        self.assertEqual(raised.exception.code, 1)


class StorageReportTests(ImageFixture):
    def test_media_kept_only_by_old_versions_and_unused_media(self):
        kept = self.uploaded()
        self.edit(f"![圖]({kept['url']})\n")
        self.edit("圖拿掉了\n")
        self.uploaded(picture(color=(9, 9, 9)))  # pasted, never saved
        storage = self.client.get("/api/admin/broken-links/").json()["storage"]
        self.assertEqual([(item["kind"], item["id"], item["versions"]) for item in storage["old_versions"]], [("image", kept["id"], [2])])
        self.assertEqual(storage["old_versions_bytes"], kept["size"])
        self.assertEqual(storage["unused"]["images"], 1)
        # In the trash, a document's media is not listed.
        self.client.delete(f"/api/documents/{self.doc}/")
        storage = self.client.get("/api/admin/broken-links/").json()["storage"]
        self.assertEqual((storage["old_versions"], storage["unused"]["images"]), ([], 0))
