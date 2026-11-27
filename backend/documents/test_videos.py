import io
import os
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from . import videos
from .models import DocumentVideo, SiteSettings, VersionVideo
from .test_images import ImageFixture, picture
from .videos import VideoUploadThrottle


def mp4(seed=b"a", brand=b"isom", size=4096):
    """A file with a real MP4 header: an ftyp box followed by filler."""
    head = (24).to_bytes(4, "big") + b"ftyp" + brand + b"\x00\x00\x02\x00" + b"isomiso2"
    return head + (seed * size)[: size - len(head)]


def webm(doctype=b"webm", seed=b"w"):
    # EBML header with a DocType element (0x4282), as written by browsers and ffmpeg.
    header = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\x82" + bytes([0x80 | len(doctype)]) + doctype
    return header + seed * 2048


class VideoFixture(ImageFixture):
    def upload_video(self, data, document=None, name="clip.mp4", client=None):
        return (client or self.client).post(
            f"/api/documents/{document or self.doc}/videos/", {"file": SimpleUploadedFile(name, data)},
        )

    def video(self, data=None, document=None):
        response = self.upload_video(data or mp4(), document)
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.json()


class VideoTests(VideoFixture):
    """P10a: videos embedded in Markdown, uploaded as they are and served by nginx after an access check."""

    # ---- upload -----------------------------------------------------------------

    def test_editor_uploads_mp4_and_gets_a_link(self):
        response = self.upload_video(mp4())
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["url"], f"/api/videos/{body['id']}/")
        self.assertEqual((body["format"], body["size"]), ("mp4", 4096))
        video = DocumentVideo.objects.get(pk=body["id"])
        stored = self.storage / video.path
        self.assertEqual(stored.read_bytes(), mp4())
        # nginx reads through the shared group; nobody else can.
        self.assertEqual(stored.stat().st_mode & 0o777, 0o640)
        self.assertEqual(stored.parent.stat().st_mode & 0o777, 0o750)
        self.assertEqual(list(stored.parent.glob(".upload-*")), [])

    def test_webm_is_accepted(self):
        self.assertEqual(self.video(webm())["format"], "webm")

    def test_format_comes_from_the_header_not_the_name(self):
        self.assertEqual(self.video(webm(), )["format"], "webm")
        self.assertEqual(self.upload_video(mp4(), name="clip.webm").json()["format"], "mp4")
        refused = {
            "QuickTime .mov": mp4(brand=b"qt  "),
            "Matroska": webm(b"matroska"),
            "image": picture(),
            "text named .mp4": b"<html><script>alert(1)</script></html>" * 10,
        }
        for label, data in refused.items():
            with self.subTest(label):
                response = self.upload_video(data)
                self.assertEqual(response.status_code, 400)
                self.assertIn("MP4", str(response.json()))
        self.assertEqual(DocumentVideo.objects.count(), 2)
        self.assertEqual(list((self.storage / "videos" / self.doc).glob(".upload-*")), [])

    def test_empty_and_oversized_files_are_refused(self):
        self.assertEqual(self.upload_video(b"").status_code, 400)
        # P23c: the admin's video limit, in MB; shrink a "megabyte" so the smallest setting (10) is 1000 bytes.
        SiteSettings.objects.update_or_create(pk=1, defaults={"video_max_mb": 10})
        with patch("documents.limits.MB", 100):
            response = self.upload_video(mp4())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["file"], "影片超過上限 10 MB。")
        self.assertFalse(DocumentVideo.objects.exists())

    def test_low_disk_space_refuses_the_upload(self):
        with override_settings(UPLOAD_MIN_FREE_BYTES=10 ** 18), self.assertLogs("documents.quota", "ERROR"):
            response = self.upload_video(mp4())
        self.assertEqual(response.status_code, 413)
        self.assertIn("磁碟空間不足", str(response.json()))
        self.assertFalse(DocumentVideo.objects.exists())

    def test_viewer_and_visitor_cannot_upload(self):
        self.assertEqual(self.upload_video(mp4(), client=self.as_user(self.viewer)).status_code, 403)
        self.assertEqual(self.upload_video(mp4(), client=self.as_user()).status_code, 403)
        self.assertFalse(DocumentVideo.objects.exists())

    def test_only_active_markdown_documents_take_videos(self):
        html = self.client.post("/api/documents/", {"file": SimpleUploadedFile("page.html", b"<p>x</p>")}).json()["id"]
        self.assertEqual(self.upload_video(mp4(), html).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.upload_video(mp4()).status_code, 404)

    def test_same_file_twice_in_one_document_is_stored_once(self):
        first = self.video()
        DocumentVideo.objects.filter(pk=first["id"]).update(uploaded_at=timezone.now() - timedelta(hours=5))
        again = self.upload_video(mp4())
        self.assertEqual((again.status_code, again.json()["id"]), (200, first["id"]))
        self.assertGreater(DocumentVideo.objects.get().uploaded_at, timezone.now() - timedelta(minutes=1))
        self.assertEqual(len(list((self.storage / "videos" / self.doc).iterdir())), 1)
        other = self.create("# 另一份\n", "other.md")
        self.assertNotEqual(self.video(document=other)["id"], first["id"])

    def test_uploads_are_rate_limited(self):
        original = VideoUploadThrottle.rate
        VideoUploadThrottle.rate = "2/hour"
        self.addCleanup(setattr, VideoUploadThrottle, "rate", original)
        self.assertEqual(self.upload_video(mp4(b"1")).status_code, 201)
        self.assertEqual(self.upload_video(mp4(b"2")).status_code, 201)
        self.assertEqual(self.upload_video(mp4(b"3")).status_code, 429)

    # ---- references -----------------------------------------------------------

    def test_versions_record_their_own_videos(self):
        mine = self.video()["id"]
        other_doc = self.create("# 別人\n", "other.md")
        theirs = self.video(mp4(b"z"), other_doc)["id"]
        version = self.edit(f"![示範](/api/videos/{mine}/)\n\n[連結](http://host/api/videos/{theirs}/)\n")
        self.assertEqual(list(VersionVideo.objects.filter(version_id=version).values_list("video_id", flat=True)),
                         [DocumentVideo.objects.get(pk=mine).pk])

    def test_uploading_a_markdown_file_and_restoring_record_references(self):
        video = self.video()["id"]
        response = self.client.post(f"/api/documents/{self.doc}/versions/", {
            "file": SimpleUploadedFile("doc.md", f"![v](/api/videos/{video}/)\n".encode()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        with_video = self.current()
        self.edit("沒有影片了\n")
        response = self.client.post(f"/api/documents/{self.doc}/versions/{with_video}/restore/",
                                    {"base_version": self.current()}, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(VersionVideo.objects.filter(version_id=self.current(), video_id=video).exists())

    # ---- reading ----------------------------------------------------------------

    def test_members_get_an_nginx_redirect_with_safe_headers(self):
        video = DocumentVideo.objects.get(pk=self.video()["id"])
        response = self.as_user(self.viewer).get(f"/api/videos/{video.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["X-Accel-Redirect"], f"/_protected/videos/{self.doc}/{video.pk}.mp4")
        self.assertEqual(response["Content-Type"], "video/mp4")
        self.assertEqual(response["Content-Disposition"], 'inline; filename="video.mp4"')
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, max-age=600")
        self.assertIn("Cookie", response["Vary"])

    def test_visitors_see_only_videos_of_the_published_version(self):
        video = self.video()["id"]
        url = f"/api/videos/{video}/"
        self.assertEqual(self.as_user().get(url).status_code, 404)
        published = self.edit(f"![v](/api/videos/{video}/)\n")
        self.publish(published)
        self.assertEqual(self.as_user().get(url).status_code, 200)
        # A newer draft without the video does not hide it while the published version still has it.
        self.edit("草稿\n")
        self.assertEqual(self.as_user().get(url).status_code, 200)
        self.assertEqual(self.as_user(self.admin).delete(f"/api/documents/{self.doc}/publication/").status_code, 204)
        self.assertEqual(self.as_user().get(url).status_code, 404)

    def test_publishing_another_document_never_exposes_this_ones_videos(self):
        video = self.video()["id"]
        other = self.create("# 公開\n")
        self.publish(self.edit(f"![v](/api/videos/{video}/)\n", other), other)
        self.assertEqual(self.as_user().get(f"/api/videos/{video}/").status_code, 404)

    def test_trashed_documents_hide_their_videos(self):
        video = self.video()["id"]
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        self.assertEqual(self.as_user(self.admin).get(f"/api/videos/{video}/").status_code, 404)

    def test_unknown_and_missing_videos_are_404(self):
        self.assertEqual(self.client.get("/api/videos/00000000-0000-0000-0000-000000000000/").status_code, 404)
        video = DocumentVideo.objects.get(pk=self.video()["id"])
        (self.storage / video.path).unlink()
        self.assertEqual(self.client.get(f"/api/videos/{video.pk}/").status_code, 404)

    # ---- deletion ---------------------------------------------------------------

    def test_permanent_deletion_removes_videos_and_files(self):
        video = self.video()["id"]
        self.edit(f"![v](/api/videos/{video}/)\n")
        self.assertEqual(self.client.delete(f"/api/documents/{self.doc}/").status_code, 204)
        response = self.as_user(self.admin).post(f"/api/trash/{self.doc}/delete/", {"title": "doc", "confirm": True},
                                                 content_type="application/json")
        self.assertIn(response.status_code, (200, 204), response.content)
        self.assertFalse(DocumentVideo.objects.exists())
        self.assertFalse(VersionVideo.objects.exists())
        self.assertFalse((self.storage / "videos" / str(self.doc)).exists())

    def test_deleting_a_version_leaves_the_video_to_the_cleanup(self):
        video = self.video()["id"]
        with_video = self.edit(f"![v](/api/videos/{video}/)\n")
        self.edit("沒有影片\n")
        response = self.as_user(self.admin).post(f"/api/documents/{self.doc}/versions/{with_video}/delete/",
                                                 {"number": 2}, content_type="application/json")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(VersionVideo.objects.exists())
        self.assertTrue(DocumentVideo.objects.filter(pk=video).exists())


class UnusedVideoTests(VideoFixture):
    """Videos no version refers to go 24 hours after their last upload, like images."""

    def age(self, video_id, hours):
        DocumentVideo.objects.filter(pk=video_id).update(uploaded_at=timezone.now() - timedelta(hours=hours))

    def collect(self, *args):
        output = io.StringIO()
        call_command("collect_unused_images", *args, stdout=output)
        return output.getvalue()

    def test_unused_videos_go_after_24_hours_only(self):
        old, recent = (self.video(mp4(seed))["id"] for seed in (b"1", b"2"))
        self.age(old, 25)
        self.age(recent, 23)
        old_file = self.storage / DocumentVideo.objects.get(pk=old).path
        self.assertIn("Removed 1 unused videos", self.collect())
        self.assertFalse(DocumentVideo.objects.filter(pk=old).exists())
        self.assertFalse(old_file.exists())
        self.assertTrue(DocumentVideo.objects.filter(pk=recent).exists())

    def test_videos_any_version_refers_to_are_kept(self):
        video = self.video()["id"]
        self.edit(f"![v](/api/videos/{video}/)\n")
        self.edit("影片拿掉了\n")
        self.age(video, 100)
        self.collect()
        self.assertTrue(DocumentVideo.objects.filter(pk=video).exists())

    def test_dry_run_changes_nothing(self):
        video = self.video()["id"]
        self.age(video, 30)
        self.assertIn("Would remove 1 unused videos", self.collect("--dry-run"))
        self.assertTrue(DocumentVideo.objects.filter(pk=video).exists())

    def test_abandoned_partial_uploads_are_removed(self):
        self.video()
        folder = self.storage / "videos" / self.doc
        stale, fresh = folder / ".upload-stale", folder / ".upload-fresh"
        stale.write_bytes(b"x")
        fresh.write_bytes(b"x")
        old = (timezone.now() - timedelta(hours=30)).timestamp()
        os.utime(stale, (old, old))
        self.collect()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_uploads_trigger_the_video_cleanup_too(self):
        with patch.object(videos, "collect_unused_videos", wraps=videos.collect_unused_videos) as collect:
            self.video()
        collect.assert_called_once()

    def test_storage_check_covers_video_files(self):
        video = DocumentVideo.objects.get(pk=self.video()["id"])
        stray = (self.storage / video.path).parent / "00000000-0000-0000-0000-000000000000.mp4"
        stray.write_bytes(b"x")
        output = io.StringIO()
        call_command("check_document_storage", stdout=output)
        self.assertIn(f"videos/{self.doc}/{stray.name}", output.getvalue())

    def test_system_status_and_maintenance_report_videos(self):
        used = self.video(mp4(b"u"))
        unused = self.video(mp4(b"n"))
        self.edit(f"![v](/api/videos/{used['id']}/)\n")
        self.age(unused["id"], 30)
        admin = self.as_user(self.admin)
        report = admin.get("/api/admin/system/").json()
        self.assertEqual(report["content"]["videos"], 2)
        self.assertEqual(report["storage"]["videos_bytes"], used["size"] + unused["size"])
        self.assertEqual((report["jobs"]["unused_videos"], report["jobs"]["unused_videos_bytes"]), (1, unused["size"]))
        results = admin.post("/api/admin/system/maintenance/").json()["results"]
        self.assertEqual(results["videos"], {"removed": 1, "bytes": unused["size"]})
