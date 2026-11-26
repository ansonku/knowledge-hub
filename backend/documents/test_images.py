import io
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from users.models import User

from . import images
from .images import ImageUploadThrottle
from .models import DocumentImage, VersionImage


def picture(fmt="PNG", size=(4, 3), color=(200, 30, 30), **save):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt, **save)
    return buffer.getvalue()


def jpeg_with_gps():
    image = Image.new("RGB", (6, 4), (10, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {2: (25.0, 2.0, 0.0), 4: (121.0, 33.0, 0.0)}  # GPS latitude / longitude
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def animated_gif():
    frames = [Image.new("RGB", (5, 5), color) for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    buffer = io.BytesIO()
    frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=80, loop=0)
    return buffer.getvalue()


class ImageFixture(TransactionTestCase):
    """A Markdown document, three members and a private storage folder."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        settings = override_settings(DOCUMENT_STORAGE=str(self.storage))
        settings.enable()
        self.addCleanup(settings.disable)
        cache.clear()
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.viewer = User.objects.create_user("reader", "reader@example.test")
        self.client.force_login(self.editor)
        self.doc = self.create("# 文件\n")

    def create(self, content, name="doc.md"):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile(name, content.encode())})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def as_user(self, user=None):
        client = Client()
        if user:
            client.force_login(user)
        return client

    def upload(self, data, document=None, name="paste.png", client=None):
        return (client or self.client).post(
            f"/api/documents/{document or self.doc}/images/", {"file": SimpleUploadedFile(name, data)},
        )

    def uploaded(self, data=None, document=None):
        response = self.upload(data or picture(), document)
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.json()

    def current(self, document=None):
        return self.client.get(f"/api/documents/{document or self.doc}/").json()["current_version"]["id"]

    def edit(self, text, document=None):
        document = document or self.doc
        response = self.client.post(f"/api/documents/{document}/markdown/", {
            "file": SimpleUploadedFile("doc.md", text.encode()), "base_version": self.current(document),
        })
        self.assertEqual(response.status_code, 201, response.content)
        return self.current(document)

    def publish(self, version, document=None):
        admin = self.as_user(self.admin)
        response = admin.post(f"/api/documents/{document or self.doc}/publication/", {"version": version, "title": "doc"},
                              content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)


class ImageTests(ImageFixture):
    """P7b images pasted into Markdown: upload checks, re-encoding, references and access."""

    # ---- upload -----------------------------------------------------------------

    def test_editor_uploads_png_and_gets_a_link(self):
        response = self.upload(picture())
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["format"], body["width"], body["height"]), ("png", 4, 3))
        self.assertEqual(body["url"], f"/api/images/{body['id']}/")
        image = DocumentImage.objects.get(pk=body["id"])
        self.assertTrue((self.storage / image.path).is_file())
        self.assertEqual(image.created_by, self.editor)

    def test_viewer_cannot_upload(self):
        self.assertEqual(self.upload(picture(), client=self.as_user(self.viewer)).status_code, 403)
        self.assertEqual(self.upload(picture(), client=self.as_user()).status_code, 403)
        self.assertFalse(DocumentImage.objects.exists())

    def test_only_active_documents_take_images(self):
        # P22: HTML documents take pictures too, for their cover.
        html = self.create("<p>x</p>", name="page.html")
        self.assertEqual(self.upload(picture(), html).status_code, 201)
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.upload(picture()).status_code, 404)

    def test_format_comes_from_content_not_name(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual(self.upload(svg, name="evil.png").status_code, 400)
        self.assertEqual(self.upload(b"<html><script>alert(1)</script></html>", name="a.gif").status_code, 400)
        self.assertEqual(self.upload(b"%PDF-1.7 not an image", name="a.jpg").status_code, 400)
        # A real JPEG named .png is accepted and stored as JPEG.
        response = self.upload(picture("JPEG"), name="wrong.png")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["format"], "jpeg")

    def test_damaged_empty_and_oversized_files_are_refused(self):
        self.assertEqual(self.upload(picture()[:40]).status_code, 400)
        self.assertEqual(self.upload(b"").status_code, 400)
        self.assertEqual(self.upload(b"\x89PNG\r\n\x1a\n" + b"\0" * (10 * 1024 * 1024)).status_code, 400)

    def test_too_many_pixels_is_refused(self):
        # A tiny file that claims 8000 × 6000 pixels (a decompression bomb in miniature).
        big = picture(size=(8000, 6000), color=(0, 0, 0))
        response = self.upload(big)
        self.assertEqual(response.status_code, 400)
        self.assertIn("4000 萬", response.json()["file"])

    def test_reencoding_strips_exif_and_applies_orientation(self):
        body = self.uploaded(jpeg_with_gps())
        # Orientation 6 rotates the 6 × 4 picture to 4 × 6.
        self.assertEqual((body["width"], body["height"]), (4, 6))
        stored = (self.storage / DocumentImage.objects.get(pk=body["id"]).path).read_bytes()
        with Image.open(io.BytesIO(stored)) as image:
            self.assertEqual(len(image.getexif()), 0)
        self.assertNotIn(b"PhoneMaker", stored)

    def test_animation_is_kept(self):
        body = self.uploaded(animated_gif())
        stored = (self.storage / DocumentImage.objects.get(pk=body["id"]).path).read_bytes()
        with Image.open(io.BytesIO(stored)) as image:
            self.assertEqual(image.n_frames, 3)

    def test_webp_is_accepted(self):
        self.assertEqual(self.uploaded(picture("WEBP"))["format"], "webp")

    def test_same_picture_twice_in_one_document_is_stored_once(self):
        first = self.upload(picture())
        second = self.upload(picture())
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["id"], second.json()["id"])
        other = self.create("# 另一份\n")
        self.assertNotEqual(self.uploaded(picture(), other)["id"], first.json()["id"])
        self.assertEqual(DocumentImage.objects.count(), 2)

    def test_uploads_are_rate_limited(self):
        original = ImageUploadThrottle.rate
        ImageUploadThrottle.rate = "2/hour"
        self.addCleanup(setattr, ImageUploadThrottle, "rate", original)
        self.assertEqual(self.upload(picture(color=(1, 1, 1))).status_code, 201)
        self.assertEqual(self.upload(picture(color=(2, 2, 2))).status_code, 201)
        self.assertEqual(self.upload(picture(color=(3, 3, 3))).status_code, 429)

    # ---- references -----------------------------------------------------------

    def test_versions_record_their_own_images_in_any_link_style(self):
        a, b, c = (self.uploaded(picture(color=(n, 0, 0)))["id"] for n in (1, 2, 3))
        foreign = self.uploaded(picture(color=(9, 9, 9)), self.create("# 別份\n"))["id"]
        version = self.edit(
            f"![a](/api/images/{a}/)\n\n"
            f'![b](https://hub.example.test/api/images/{b}/ "標題")\n\n'
            f"![c][ref]\n\n[ref]: /api/images/{c}/\n\n"
            f"![other](/api/images/{foreign}/)\n"
        )
        recorded = set(VersionImage.objects.filter(version_id=version).values_list("image_id", flat=True))
        self.assertEqual({str(pk) for pk in recorded}, {a, b, c})

    def test_uploading_a_markdown_file_and_restoring_record_references(self):
        image = self.uploaded()["id"]
        response = self.client.post(f"/api/documents/{self.doc}/versions/", {
            "file": SimpleUploadedFile("doc.md", f"![x](/api/images/{image}/)\n".encode()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        with_image = self.current()
        self.assertTrue(VersionImage.objects.filter(version_id=with_image).exists())
        self.edit("沒有圖片了\n")
        response = self.client.post(f"/api/documents/{self.doc}/versions/{with_image}/restore/",
                                    {"base_version": self.current()}, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(VersionImage.objects.filter(version_id=self.current(), image_id=image).exists())

    # ---- reading ----------------------------------------------------------------

    def test_members_read_images_with_safe_headers(self):
        image = self.uploaded()["id"]
        for user in (self.viewer, self.editor, self.admin):
            response = self.as_user(user).get(f"/api/images/{image}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response["Content-Security-Policy"], "default-src 'none'; sandbox")
            self.assertTrue(response["Content-Disposition"].startswith("inline"))
            self.assertIn("private", response["Cache-Control"])
            self.assertEqual(b"".join(response.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")

    def test_visitors_see_only_images_of_the_published_version(self):
        shown, hidden, later = (self.uploaded(picture(color=(n, 5, 5)))["id"] for n in (1, 2, 3))
        visitor = self.as_user()
        self.assertEqual(visitor.get(f"/api/images/{shown}/").status_code, 404)
        published = self.edit(f"![s](/api/images/{shown}/)\n")
        self.publish(published)
        self.edit(f"![s](/api/images/{shown}/)\n![l](/api/images/{later}/)\n")
        self.assertEqual(visitor.get(f"/api/images/{shown}/").status_code, 200)
        # Uploaded but never published, or only in a newer draft version: not public.
        self.assertEqual(visitor.get(f"/api/images/{hidden}/").status_code, 404)
        self.assertEqual(visitor.get(f"/api/images/{later}/").status_code, 404)
        # Withdrawn: gone at once.
        self.assertEqual(self.as_user(self.admin).delete(f"/api/documents/{self.doc}/publication/").status_code, 204)
        self.assertEqual(visitor.get(f"/api/images/{shown}/").status_code, 404)

    def test_publishing_another_document_never_exposes_this_ones_images(self):
        private = self.uploaded()["id"]
        other = self.create("# 公開文件\n")
        self.publish(self.edit(f"![借用](/api/images/{private}/)\n", other), other)
        self.assertEqual(self.as_user().get(f"/api/images/{private}/").status_code, 404)

    def test_trashed_documents_hide_their_images(self):
        image = self.uploaded()["id"]
        self.publish(self.edit(f"![x](/api/images/{image}/)\n"))
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.as_user(self.viewer).get(f"/api/images/{image}/").status_code, 404)
        self.assertEqual(self.as_user().get(f"/api/images/{image}/").status_code, 404)

    def test_unknown_and_missing_images_are_404(self):
        self.assertEqual(self.client.get("/api/images/00000000-0000-0000-0000-000000000000/").status_code, 404)
        image = DocumentImage.objects.get(pk=self.uploaded()["id"])
        (self.storage / image.path).unlink()
        self.assertEqual(self.client.get(f"/api/images/{image.pk}/").status_code, 404)

    # ---- deletion ---------------------------------------------------------------

    def test_permanent_deletion_removes_images_and_files(self):
        image = DocumentImage.objects.get(pk=self.uploaded()["id"])
        self.edit(f"![x](/api/images/{image.pk}/)\n")
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        title = "doc"
        response = self.as_user(self.admin).post(f"/api/trash/{self.doc}/delete/", {"title": title, "confirm": True},
                                                 content_type="application/json")
        self.assertIn(response.status_code, (200, 204), response.content)
        self.assertFalse(DocumentImage.objects.exists())
        self.assertFalse(VersionImage.objects.exists())
        self.assertFalse((self.storage / "images" / str(self.doc)).exists())


class UnusedImageTests(ImageFixture):
    """P7c: images no version refers to are removed after 24 hours; referenced ones never are."""

    def age(self, image_id, hours):
        DocumentImage.objects.filter(pk=image_id).update(uploaded_at=timezone.now() - timedelta(hours=hours))

    def file(self, image_id):
        return self.storage / DocumentImage.objects.get(pk=image_id).path

    def collect(self, *args):
        output = io.StringIO()
        call_command("collect_unused_images", *args, stdout=output)
        return output.getvalue()

    def test_unused_images_go_after_24_hours_only(self):
        old, recent = (self.uploaded(picture(color=(n, 1, 1)))["id"] for n in (1, 2))
        old_file = self.file(old)
        self.age(old, 25)
        self.age(recent, 23)
        self.assertIn("Removed 1 unused images", self.collect())
        self.assertFalse(DocumentImage.objects.filter(pk=old).exists())
        self.assertFalse(old_file.exists())
        self.assertTrue(DocumentImage.objects.filter(pk=recent).exists())

    def test_images_any_version_refers_to_are_kept(self):
        kept = self.uploaded()["id"]
        self.edit(f"![x](/api/images/{kept}/)\n")
        self.edit("圖片在新版本被刪掉了\n")
        self.age(kept, 24 * 365)
        self.collect()
        self.assertTrue(DocumentImage.objects.filter(pk=kept).exists())
        self.assertTrue(self.file(kept).exists())
        self.assertEqual(self.client.get(f"/api/images/{kept}/").status_code, 200)

    def test_dry_run_changes_nothing(self):
        image = self.uploaded()["id"]
        self.age(image, 48)
        self.assertIn("Would remove 1 unused images", self.collect("--dry-run"))
        self.assertTrue(self.file(image).exists())

    def test_pasting_again_restarts_the_grace_period(self):
        image = self.uploaded()["id"]
        self.age(image, 30)
        self.assertEqual(self.upload(picture()).status_code, 200)
        self.collect()
        self.assertTrue(DocumentImage.objects.filter(pk=image).exists())

    def test_uploads_trigger_the_cleanup_at_most_hourly(self):
        stale = self.uploaded(picture(color=(5, 5, 5)))["id"]
        self.age(stale, 30)
        cache.clear()
        with patch.object(images, "collect_unused_images", wraps=images.collect_unused_images) as collect:
            self.uploaded(picture(color=(6, 6, 6)))
            self.uploaded(picture(color=(7, 7, 7)))
        self.assertEqual(collect.call_count, 1)
        self.assertFalse(DocumentImage.objects.filter(pk=stale).exists())

    def test_cleanup_failure_never_fails_the_upload(self):
        cache.clear()
        with patch.object(images, "collect_unused_images", side_effect=RuntimeError("disk")), self.assertLogs("documents.images", "ERROR"):
            self.assertEqual(self.upload(picture()).status_code, 201)

    def test_the_last_image_takes_its_empty_folder_with_it(self):
        image = self.uploaded()["id"]
        folder = self.file(image).parent
        self.age(image, 30)
        self.collect()
        self.assertFalse(folder.exists())

    def test_storage_check_covers_image_files(self):
        image = self.uploaded()["id"]
        stray = self.file(image).parent / "00000000-0000-0000-0000-000000000000.png"
        stray.write_bytes(b"x")
        output = io.StringIO()
        call_command("check_document_storage", "--quarantine", stdout=output)
        self.assertIn(f"Unreferenced: images/{self.doc}/{stray.name}", output.getvalue())
        self.assertFalse(stray.exists())
        self.assertTrue((self.storage / "quarantine" / "images" / str(self.doc) / stray.name).exists())
        self.file(image).unlink()
        with self.assertRaises(CommandError):
            call_command("check_document_storage", stdout=io.StringIO(), stderr=io.StringIO())

    def test_system_status_reports_images(self):
        used = self.uploaded(picture(color=(8, 8, 8)))
        unused = self.uploaded(picture(color=(9, 9, 9)))
        self.age(unused["id"], 30)
        report = self.as_user(self.admin).get("/api/admin/system/").json()
        self.assertEqual(report["content"]["images"], 2)
        self.assertEqual(report["storage"]["images_bytes"], used["size"] + unused["size"])
        self.assertEqual((report["jobs"]["unused_images"], report["jobs"]["unused_images_bytes"]), (1, unused["size"]))
