from django.core.files.uploadedfile import SimpleUploadedFile

from .test_images import ImageFixture, picture


class ImageSizeTests(ImageFixture):
    """P11b: gallery layouts get each picture's shape before it loads, within the usual read rules."""

    def test_members_get_every_image_of_the_document(self):
        saved = self.uploaded(picture(size=(40, 30)))
        pending = self.uploaded(picture(size=(10, 50), color=(1, 2, 3)))  # pasted, not saved in any version yet
        self.edit(f"![a]({saved['url']})\n")
        response = self.as_user(self.viewer).get(f"/api/documents/{self.doc}/image-sizes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {saved["id"]: [40, 30], pending["id"]: [10, 50]})

    def test_visitors_and_trashed_documents_get_nothing(self):
        self.uploaded()
        self.assertEqual(self.as_user().get(f"/api/documents/{self.doc}/image-sizes/").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/documents/{self.doc}/image-sizes/").status_code, 404)

    def test_public_article_lists_only_images_of_the_published_version(self):
        published = self.uploaded(picture(size=(60, 20)))
        later = self.uploaded(picture(size=(20, 60), color=(9, 9, 9)))
        other = self.create("# 別人\n", "other.md")
        borrowed = self.uploaded(picture(size=(33, 33), color=(5, 5, 5)), other)
        version = self.edit(f"![p]({published['url']})\n![b]({borrowed['url']})\n")
        self.publish(version)
        self.edit(f"![p]({published['url']})\n![l]({later['url']})\n")
        body = self.as_user().get(f"/api/public/articles/{self.doc}/").json()
        self.assertEqual(body["image_sizes"], {published["id"]: [60, 20]})

    def test_reading_portal_uses_the_current_version(self):
        first = self.uploaded(picture(size=(12, 34)))
        self.edit(f"![f]({first['url']})\n")
        body = self.as_user(self.viewer).get(f"/api/read/articles/{self.doc}/").json()
        self.assertEqual(body["image_sizes"], {first["id"]: [12, 34]})

    def test_html_documents_have_none(self):
        html = self.client.post("/api/documents/", {"file": SimpleUploadedFile("p.html", b"<p>x</p>")}).json()["id"]
        self.assertEqual(self.as_user(self.viewer).get(f"/api/read/articles/{html}/").json()["image_sizes"], {})
