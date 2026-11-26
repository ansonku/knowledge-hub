"""P21b: album articles carry a cover (first own picture as a thumbnail) and a picture count on cards and in the nav."""
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

from .models import Document
from .test_images import ImageFixture, picture
from .test_popularity import PopularityFixture


class CoverTests(ImageFixture):
    def setUp(self):
        super().setUp()
        self.first = self.uploaded(picture(size=(800, 500)))
        self.second = self.uploaded(picture(size=(800, 500), color=(1, 2, 3)))
        self.other_doc = self.create("# 別份\n", "別份.md")
        self.foreign = self.uploaded(picture(size=(800, 500), color=(4, 5, 6)), self.other_doc)
        Document.objects.filter(pk=self.doc).update(presentation=Document.Presentation.GALLERY)
        self.plain = self.create("# 一般\n\n內文。\n", "一般.md")

    def album_body(self, *pictures):
        return ":::gallery grid\n" + "\n".join(f"![p]({item['url']})" for item in pictures) + "\n:::\n"

    def card(self, rows, pk):
        return next(row for row in rows if str(row.get("document_id") or row.get("id")) == str(pk))

    def test_public_cards_use_the_published_version(self):
        self.publish(self.edit(self.album_body(self.foreign, self.second)))
        self.edit(self.album_body(self.first, self.second))  # not published
        rows = self.as_user().get("/api/public/articles/").json()["results"]
        card = self.card(rows, self.doc)
        # Another document's picture is not this album's own; the draft's first picture is not public.
        self.assertEqual(card["cover"], {"url": f"/api/images/{self.second['id']}/thumb/", "count": 1})
        self.assertEqual(card["excerpt"], "相簿 · 1 張圖片")
        nav = self.card(self.as_user().get("/api/public/nav/").json()["articles"], self.doc)
        self.assertEqual(nav["cover"]["url"], card["cover"]["url"])

    def test_portal_uses_the_current_version(self):
        self.edit(self.album_body(self.first, self.second, self.first))
        card = self.card(self.as_user(self.viewer).get("/api/read/articles/").json()["results"], self.doc)
        self.assertEqual(card["cover"], {"url": f"/api/images/{self.first['id']}/thumb/", "count": 2})
        nav = self.card(self.as_user(self.viewer).get("/api/read/nav/").json()["articles"], self.doc)
        self.assertEqual(nav["cover"]["count"], 2)

    def test_ordinary_articles_and_empty_albums(self):
        self.edit("# 空相簿\n\n還沒有圖片。\n")
        rows = self.as_user(self.viewer).get("/api/read/articles/").json()["results"]
        self.assertNotIn("cover", self.card(rows, self.plain))
        empty = self.card(rows, self.doc)
        self.assertEqual((empty["cover"], empty["excerpt"]), ({"url": None, "count": 0}, "相簿"))

    def test_gallery_syntax_never_shows_in_excerpts(self):
        self.edit(":::gallery justified\n![p](/api/images/x/)\n:::\n\n說明文字。\n", self.plain)
        card = self.card(self.as_user(self.viewer).get("/api/read/articles/").json()["results"], self.plain)
        self.assertNotIn(":::", card["excerpt"])
        self.assertNotIn("justified", card["excerpt"])  # the layout name goes with the fence
        self.assertIn("說明文字", card["excerpt"])


class StartupImportTests(SimpleTestCase):
    """The server imports hub.urls first; a cycle that tests miss (their import order differs) stops it from starting."""

    def test_urls_import_in_a_fresh_process(self):
        result = subprocess.run([sys.executable, "-c", "import django; django.setup(); import hub.urls"], capture_output=True, text=True,
                                env={**os.environ, "DJANGO_SETTINGS_MODULE": "hub.settings"}, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr[-800:])


class PopularCoverTests(PopularityFixture):
    """P21b: popular and featured articles carry the album cover too."""

    def test_popular_and_featured_albums(self):
        album, *others = [self.article(title) for title in ("相簿", "甲", "乙")]
        Document.objects.filter(pk=album).update(presentation=Document.Presentation.GALLERY)
        for index, document in enumerate([album, *others]):
            for visitor in range(3 - index):
                self.view(document, f"198.51.100.{visitor + 1}")
        popular = {row["document_id"]: row for row in self.visitor.get("/api/public/popular/").json()["results"]}
        self.assertEqual((popular[album]["cover"], popular[album]["excerpt"]), ({"url": None, "count": 0}, "相簿"))
        self.assertNotIn("cover", popular[others[0]])
        self.assertEqual(self.client.put("/api/admin/featured/", {"documents": [album]}, content_type="application/json").status_code, 200)
        featured = self.visitor.get("/api/public/featured/").json()["results"]
        self.assertEqual(featured[0]["cover"]["count"], 0)
