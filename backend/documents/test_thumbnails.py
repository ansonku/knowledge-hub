"""P21a: 480 px WebP thumbnails with the image's own access rules."""
import io
from datetime import timedelta

from django.utils import timezone
from PIL import Image

from .consistency import inspect_storage
from .images import collect_unused_images, thumb_relative
from .models import DocumentImage
from .test_images import ImageFixture, picture


def animation():
    frames = [Image.new("RGB", (900, 600), color) for color in ((200, 0, 0), (0, 200, 0))]
    buffer = io.BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buffer.getvalue()


class ThumbnailTests(ImageFixture):
    def thumb(self, image, client=None):
        return (client or self.client).get(f"/api/images/{image['id']}/thumb/")

    def opened(self, response):
        return Image.open(io.BytesIO(b"".join(response.streaming_content)))

    def test_a_480_px_webp_made_once(self):
        image = self.uploaded(picture(size=(1600, 1000)))
        response = self.thumb(image)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")
        self.assertEqual(response["Cache-Control"], "private, max-age=600")
        thumb = self.opened(response)
        self.assertEqual((thumb.format, thumb.size), ("WEBP", (480, 300)))
        path = self.storage / thumb_relative(self.doc, image["id"])
        made = path.stat().st_mtime_ns
        self.assertEqual(self.thumb(image).status_code, 200)
        self.assertEqual(path.stat().st_mtime_ns, made)

    def test_small_pictures_are_not_enlarged_and_animations_give_their_first_frame(self):
        self.assertEqual(self.opened(self.thumb(self.uploaded(picture(size=(300, 200))))).size, (300, 200))
        still = self.opened(self.thumb(self.uploaded(animation())))
        self.assertEqual((still.size, getattr(still, "n_frames", 1)), ((480, 320), 1))
        self.assertEqual(still.convert("RGB").getpixel((10, 10))[0] > 150, True)

    def test_visitors_only_for_pictures_of_the_published_version(self):
        shown = self.uploaded(picture(size=(800, 500)))
        hidden = self.uploaded(picture(size=(800, 500), color=(1, 2, 3)))
        self.publish(self.edit(f"![公開]({shown['url']})\n"))
        self.edit(f"![公開]({shown['url']}) ![草稿]({hidden['url']})\n")
        visitor = self.as_user()
        self.assertEqual(self.thumb(shown, visitor).status_code, 200)
        self.assertEqual(self.thumb(hidden, visitor).status_code, 404)
        self.assertEqual(self.thumb(hidden, self.as_user(self.viewer)).status_code, 200)
        self.assertEqual(self.client.get("/api/images/99999999-9999-9999-9999-999999999999/thumb/").status_code, 404)

    def test_an_unreadable_original_is_sent_as_it_is(self):
        image = self.uploaded(picture(size=(800, 500)))
        stored = DocumentImage.objects.get(pk=image["id"])
        (self.storage / stored.path).write_bytes(b"not a picture")
        with self.assertLogs("documents.images", "ERROR"):
            response = self.thumb(image)
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/png"))

    def test_cleanup_removes_thumbnails_and_the_consistency_check_ignores_them(self):
        kept = self.uploaded(picture(size=(800, 500)))
        unused = self.uploaded(picture(size=(800, 500), color=(9, 9, 9)))
        self.edit(f"![留著]({kept['url']})\n")
        for image in (kept, unused):
            self.assertEqual(self.thumb(image).status_code, 200)
        _, _, unreferenced = inspect_storage()
        self.assertEqual(unreferenced, [])
        DocumentImage.objects.filter(pk=unused["id"]).update(uploaded_at=timezone.now() - timedelta(days=2))
        self.assertEqual(collect_unused_images()[0], 1)
        self.assertFalse((self.storage / thumb_relative(self.doc, unused["id"])).exists())
        self.assertTrue((self.storage / thumb_relative(self.doc, kept["id"])).exists())
