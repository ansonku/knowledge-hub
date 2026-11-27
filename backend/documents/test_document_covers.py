"""P22: a cover picture for any document — set, kept, public when published, on cards and as og:image."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from .images import collect_unused_images
from .models import Document, DocumentActivity, DocumentImage
from .test_images import ImageFixture, picture


@override_settings(PUBLIC_ORIGIN="https://hub.example.test")
class DocumentCoverTests(ImageFixture):
    def set_cover(self, image_id, document=None, client=None):
        return (client or self.client).patch(f"/api/documents/{document or self.doc}/", {"cover_image": image_id},
                                             content_type="application/json")

    def test_set_change_and_clear_with_activity(self):
        image = self.uploaded(picture(size=(800, 500)))
        response = self.set_cover(image["id"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["cover_image"]["thumb"], f"/api/images/{image['id']}/thumb/")
        self.assertEqual(self.client.get(f"/api/documents/{self.doc}/").json()["cover_image"]["id"], image["id"])
        self.assertEqual(self.set_cover(None).json()["cover_image"], None)
        changes = [row.detail.get("cover") for row in DocumentActivity.objects.filter(document_id=self.doc, action="metadata").order_by("created_at")]
        self.assertEqual(changes, [{"from": False, "to": True}, {"from": True, "to": False}])

    def test_only_this_documents_pictures_and_only_editors(self):
        other = self.create("# 別份\n", "別份.md")
        foreign = self.uploaded(picture(size=(800, 500), color=(1, 2, 3)), other)
        self.assertEqual(self.set_cover(foreign["id"]).status_code, 400)
        mine = self.uploaded(picture(size=(800, 500)))
        self.assertEqual(self.set_cover(mine["id"], client=self.as_user(self.viewer)).status_code, 403)

    def test_html_documents_can_upload_a_cover(self):
        page = self.client.post("/api/documents/", {"file": SimpleUploadedFile("頁面.html", b"<h1>HTML</h1>")}).json()["id"]
        image = self.uploaded(picture(size=(800, 500)), page)
        self.assertEqual(self.set_cover(image["id"], page).status_code, 200)

    def test_cleanup_keeps_the_cover_and_a_removed_picture_clears_it(self):
        cover = self.uploaded(picture(size=(800, 500)))
        loose = self.uploaded(picture(size=(800, 500), color=(9, 9, 9)))
        self.set_cover(cover["id"])
        DocumentImage.objects.filter(pk__in=[cover["id"], loose["id"]]).update(uploaded_at=timezone.now() - timedelta(days=2))
        self.assertEqual(collect_unused_images()[0], 1)
        self.assertTrue(DocumentImage.objects.filter(pk=cover["id"]).exists())
        DocumentImage.objects.filter(pk=cover["id"]).delete()
        self.assertIsNone(Document.objects.get(pk=self.doc).cover_image_id)

    def test_visitors_read_the_cover_only_while_published(self):
        cover = self.uploaded(picture(size=(800, 500)))
        other = self.uploaded(picture(size=(800, 500), color=(4, 5, 6)))
        self.set_cover(cover["id"])
        visitor = self.as_user()
        self.assertEqual(visitor.get(cover["url"]).status_code, 404)
        self.publish(self.current())
        self.assertEqual(visitor.get(cover["url"]).status_code, 200)
        self.assertEqual(visitor.get(f"{cover['url']}thumb/").status_code, 200)
        self.assertEqual(visitor.get(other["url"]).status_code, 404)  # not the cover, not in the published text
        self.as_user(self.admin).delete(f"/api/documents/{self.doc}/publication/")
        self.assertEqual(visitor.get(cover["url"]).status_code, 404)

    def test_cards_prefer_the_chosen_cover(self):
        cover = self.uploaded(picture(size=(800, 500)))
        self.set_cover(cover["id"])
        self.publish(self.edit("# 文件\n\n一般文章的內容。\n"))
        card = next(row for row in self.as_user().get("/api/public/articles/").json()["results"] if str(row["document_id"]) == self.doc)
        self.assertEqual(card["cover"], {"url": f"/api/images/{cover['id']}/thumb/", "count": None})
        self.assertIn("一般文章的內容", card["excerpt"])
        # An album keeps its picture count but shows the chosen cover instead of its first picture.
        first = self.uploaded(picture(size=(800, 500), color=(7, 7, 7)))
        Document.objects.filter(pk=self.doc).update(presentation=Document.Presentation.GALLERY)
        self.publish(self.edit(f":::gallery\n![a]({first['url']})\n:::\n"))
        card = next(row for row in self.as_user().get("/api/public/articles/").json()["results"] if str(row["document_id"]) == self.doc)
        self.assertEqual(card["cover"], {"url": f"/api/images/{cover['id']}/thumb/", "count": 1})

    def test_og_image_on_the_public_page(self):
        cover = self.uploaded(picture(size=(800, 500)))
        self.publish(self.current())
        self.assertNotIn("og:image", self.as_user().get(f"/articles/{self.doc}/")["X-Hub-Head"])
        self.set_cover(cover["id"])
        head = self.as_user().get(f"/articles/{self.doc}/")["X-Hub-Head"]
        self.assertIn(f'<meta property="og:image" content="https://hub.example.test/api/images/{cover["id"]}/">', head)
        self.assertIn('content="summary_large_image"', head)
