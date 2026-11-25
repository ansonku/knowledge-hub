from django.core.files.uploadedfile import SimpleUploadedFile

from .models import DocumentActivity
from .test_images import ImageFixture


class PresentationTests(ImageFixture):
    """P11c: a Markdown document can read as a photo album; the setting is metadata, not a version."""

    def patch(self, data, client=None, document=None):
        return (client or self.client).patch(f"/api/documents/{document or self.doc}/", data, content_type="application/json")

    def test_new_documents_read_as_articles(self):
        body = self.client.get(f"/api/documents/{self.doc}/").json()
        self.assertEqual((body["presentation"], body["gallery_layout"]), ("article", ""))

    def test_editors_switch_to_gallery_mode_without_a_new_version(self):
        version = self.current()
        response = self.patch({"presentation": "gallery", "gallery_layout": "masonry"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["presentation"], response.json()["gallery_layout"]), ("gallery", "masonry"))
        self.assertEqual(self.current(), version)
        entry = DocumentActivity.objects.filter(document_id=self.doc, action=DocumentActivity.Action.METADATA).latest("created_at")
        self.assertEqual(entry.detail, {"presentation": {"from": "article", "to": "gallery"},
                                        "gallery_layout": {"from": "", "to": "masonry"}})
        self.assertEqual(self.patch({"gallery_layout": ""}).json()["gallery_layout"], "")

    def test_viewers_and_visitors_cannot_change_it(self):
        self.assertEqual(self.patch({"presentation": "gallery"}, self.as_user(self.viewer)).status_code, 403)
        self.assertEqual(self.patch({"presentation": "gallery"}, self.as_user()).status_code, 403)
        self.assertEqual(self.client.get(f"/api/documents/{self.doc}/").json()["presentation"], "article")

    def test_only_known_values(self):
        self.assertEqual(self.patch({"presentation": "slideshow"}).status_code, 400)
        self.assertEqual(self.patch({"gallery_layout": "gird"}).status_code, 400)

    def test_html_documents_stay_articles(self):
        html = self.client.post("/api/documents/", {"file": SimpleUploadedFile("p.html", b"<p>x</p>")}).json()["id"]
        response = self.patch({"presentation": "gallery"}, document=html)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Markdown", str(response.json()))

    def test_public_article_and_reading_portal_follow_the_setting(self):
        self.publish(self.current())
        self.patch({"presentation": "gallery", "gallery_layout": "grid"})
        public = self.as_user().get(f"/api/public/articles/{self.doc}/").json()
        self.assertEqual((public["presentation"], public["gallery_layout"]), ("gallery", "grid"))
        portal = self.as_user(self.viewer).get(f"/api/read/articles/{self.doc}/").json()
        self.assertEqual((portal["presentation"], portal["gallery_layout"]), ("gallery", "grid"))
