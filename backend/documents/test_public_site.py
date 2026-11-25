import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from users.models import User

from .models import Category, Document, Tag
from .publication import reading_minutes, summarise

# Fields a visitor may receive. Anything else (descriptions, parents, internal counts,
# authors, tags, version ids) is internal and must not appear in public responses.
CARD_FIELDS = {"document_id", "title", "format", "published_at", "excerpt", "reading_minutes", "collection", "path"}
# image_sizes (P11b): ids and sizes of pictures the published body already shows, nothing else.
ARTICLE_FIELDS = {"title", "format", "body", "published_at", "reading_minutes", "collection", "path", "siblings", "image_sizes"}
NODE_FIELDS = {"id", "name", "color", "parent", "depth", "article_count", "total_count"}
COLLECTION_FIELDS = {"id", "name", "color"}


class PublicSiteTests(TransactionTestCase):
    """P3 public knowledge site APIs: article cards, collections, siblings and the /articles/ entry."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN, display_name="Secret Author")
        self.client.force_login(self.admin)
        self.visitor = Client()
        self.parent = parent = Category.objects.create(name="Internal parent", description="internal only", color="red")
        self.ops = Category.objects.create(name="Ops", parent=parent, description="hidden description", color="teal")
        # A sibling sub-collection with nothing published must never surface.
        Category.objects.create(name="Unpublished child", parent=parent, description="nope", color="blue")
        self.hidden = Category.objects.create(name="Hidden collection", description="nobody sees this")
        self.tag = Tag.objects.create(name="secret-tag")

    def upload(self, content, name="doc.md", **data):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile(name, content), **data})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def publish(self, document_id):
        document = Document.objects.get(pk=document_id)
        response = self.client.post(
            f"/api/documents/{document_id}/publication/",
            {"version": str(document.current_version_id), "title": document.title}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def get(self, url, **params):
        response = self.visitor.get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no-store", response["Cache-Control"])
        return response.json()

    def test_cards_collections_and_siblings_expose_only_public_fields(self):
        first = self.upload("# 部署指南\n\n這是**公開**的[部署](https://example.test)說明。".encode(), title="部署指南",
                            category=str(self.ops.pk), tags=[str(self.tag.pk)])
        second = self.upload(b"<html><head><title>x</title></head><body><p>HTML body text</p></body></html>",
                             name="page.html", title="HTML page", category=str(self.ops.pk))
        loose = self.upload(b"Loose article", title="Loose")
        private = self.upload(b"Private draft", title="Private", category=str(self.hidden.pk))
        for document_id in (first, second, loose):
            self.publish(document_id)

        listing = self.get("/api/public/articles/")
        self.assertEqual(listing["count"], 3)
        cards = {card["document_id"]: card for card in listing["results"]}
        self.assertEqual(set(cards), {first, second, loose})
        for card in cards.values():
            self.assertEqual(set(card), CARD_FIELDS)
            self.assertGreaterEqual(card["reading_minutes"], 1)
        self.assertEqual(cards[first]["collection"], {"id": str(self.ops.pk), "name": "Ops", "color": "teal"})
        self.assertEqual(cards[first]["path"], [{"id": str(self.parent.pk), "name": "Internal parent", "color": "red"},
                                                {"id": str(self.ops.pk), "name": "Ops", "color": "teal"}])
        self.assertEqual(cards[loose]["path"], [])
        self.assertIsNone(cards[loose]["collection"])
        # Markdown syntax and a leading title are stripped from the excerpt.
        self.assertEqual(cards[first]["excerpt"], "這是公開的部署說明。")
        # The published HTML snapshot is the readable body, so <head><title> is not part of the excerpt.
        self.assertEqual(cards[second]["excerpt"], "HTML body text")

        by_collection = self.get("/api/public/articles/", collection=str(self.ops.pk))
        self.assertEqual({card["document_id"] for card in by_collection["results"]}, {first, second})
        self.assertEqual(self.get("/api/public/articles/", collection=str(self.hidden.pk))["results"], [])
        # A parent collection lists its sub-collections' articles.
        by_parent = self.get("/api/public/articles/", collection=str(self.parent.pk))
        self.assertEqual({card["document_id"] for card in by_parent["results"]}, {first, second})
        self.assertEqual(self.visitor.get("/api/public/articles/", {"collection": "not-a-uuid"}).status_code, 400)

        collections = self.get("/api/public/collections/")["results"]
        self.assertEqual(collections, [
            {"id": str(self.parent.pk), "name": "Internal parent", "color": "red", "parent": None, "depth": 0,
             "article_count": 0, "total_count": 2},
            {"id": str(self.ops.pk), "name": "Ops", "color": "teal", "parent": str(self.parent.pk), "depth": 1,
             "article_count": 2, "total_count": 2},
        ])
        nav = self.get("/api/public/nav/")
        self.assertEqual(nav["collections"], collections)
        self.assertEqual({row["document_id"] for row in nav["articles"]}, {first, second, loose})
        self.assertEqual(set(nav["articles"][0]), {"document_id", "title", "collection_id", "published_at"})

        article = self.get(f"/api/public/articles/{first}/")
        self.assertEqual(set(article), ARTICLE_FIELDS)
        self.assertEqual(set(article["collection"]), COLLECTION_FIELDS)
        self.assertEqual([node["name"] for node in article["path"]], ["Internal parent", "Ops"])
        self.assertEqual({row["document_id"] for row in article["siblings"]}, {first, second})
        self.assertEqual(set(article["siblings"][0]), {"document_id", "title"})
        self.assertEqual(self.get(f"/api/public/articles/{loose}/")["siblings"], [])

        # Nothing internal leaks anywhere in the public responses.
        dumped = str([listing, collections, nav, article, self.get(f"/api/public/articles/{second}/")])
        for secret in ("internal only", "hidden description", "Hidden collection", "Unpublished child", "nope",
                       "nobody sees this", "Secret Author", "secret-tag", "Private draft", private):
            self.assertNotIn(secret, dumped)
        self.assertEqual(self.visitor.get(f"/api/public/articles/{private}/").status_code, 404)

    def test_withdrawn_and_trashed_articles_leave_lists_collections_and_siblings(self):
        kept = self.upload(b"Kept", title="Kept", category=str(self.ops.pk))
        withdrawn = self.upload(b"Withdrawn", title="Withdrawn", category=str(self.ops.pk))
        trashed = self.upload(b"Trashed", title="Trashed", category=str(self.hidden.pk))
        for document_id in (kept, withdrawn, trashed):
            self.publish(document_id)
        self.assertEqual(self.client.delete(f"/api/documents/{withdrawn}/publication/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/documents/{trashed}/").status_code, 204)

        self.assertEqual([card["document_id"] for card in self.get("/api/public/articles/")["results"]], [kept])
        tree = self.get("/api/public/collections/")["results"]
        self.assertEqual([(node["name"], node["article_count"], node["total_count"]) for node in tree],
                         [("Internal parent", 0, 1), ("Ops", 1, 1)])
        self.assertNotIn("Hidden collection", str(self.get("/api/public/nav/")))
        self.assertEqual([row["document_id"] for row in self.get(f"/api/public/articles/{kept}/")["siblings"]], [kept])
        for document_id in (withdrawn, trashed):
            self.assertEqual(self.visitor.get(f"/api/public/articles/{document_id}/").status_code, 404)
            self.assertEqual(self.visitor.get(f"/articles/{document_id}/").status_code, 404)

    def test_public_entry_pages_and_methods(self):
        entry = self.visitor.get("/articles/")
        self.assertEqual(entry.status_code, 200)
        self.assertEqual(entry["X-Accel-Redirect"], "/index.html")
        self.assertIn("no-store", entry["Cache-Control"])
        for url in ("/articles/", "/api/public/articles/", "/api/public/collections/"):
            self.assertEqual(self.visitor.post(url).status_code, 405)

    def test_excerpt_and_reading_time_helpers(self):
        self.assertEqual(summarise("Title: body", "Title", "md"), "body")
        self.assertTrue(summarise("字" * 300, "", "md").endswith("…"))
        self.assertEqual(len(summarise("字" * 300, "", "md")), 121)
        self.assertEqual(summarise("```code block``` after", "", "md"), "after")
        table = "| 代碼 | 名稱 |\n|---|:---:|\n| 0x01 | INVALID_CHANNEL |"
        self.assertEqual(summarise(table, "", "md"), "代碼 名稱 0x01 INVALID_CHANNEL")
        self.assertEqual(summarise("_強調_ 與 __粗體__ 與 snake_case", "", "md"), "強調 與 粗體 與 snake_case")
        self.assertEqual(reading_minutes("", 0), 1)
        self.assertEqual(reading_minutes("字" * 100, 4000), 10)
        self.assertEqual(reading_minutes("a" * 100, 4000), 4)

    def test_entry_pages_send_escaped_ascii_head_for_published_articles_only(self):
        hostile = '"><script>alert(1)</script> 部署 & <b>'
        article = self.upload(b"# Body\n\nSummary with <img src=x onerror=alert(2)> text", title=hostile)
        page = f"/articles/{article}/"
        self.assertEqual(self.visitor.get(page).status_code, 404)
        self.publish(article)

        response = self.visitor.get(page)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], "/index.html")
        head = response["X-Hub-Head"]
        self.assertTrue(head.isascii())
        self.assertNotIn("<script", head)
        self.assertNotIn("<img", head)
        self.assertIn("&lt;script&gt;", head)
        self.assertIn("&#37096;&#32626;", head)  # 部署
        self.assertIn("&amp;", head)
        self.assertIn('<meta property="og:type" content="article">', head)
        self.assertIn(f'<meta property="og:url" content="http://localhost:18080/articles/{article}/">', head)
        # Every attribute value stays inside its quotes.
        self.assertEqual(head.count('"'), 2 * head.count('content="') + 2 * head.count('name="') + 2 * head.count('property="'))

        home = self.visitor.get("/articles/")
        self.assertIn('<meta property="og:type" content="website">', home["X-Hub-Head"])
        self.assertTrue(home["X-Hub-Head"].startswith("<title>"))

        self.assertEqual(self.client.delete(f"/api/documents/{article}/publication/").status_code, 204)
        withdrawn = self.visitor.get(page)
        self.assertEqual(withdrawn.status_code, 404)
        self.assertFalse(withdrawn.has_header("X-Hub-Head"))

    def test_head_text_is_bounded(self):
        from .publication import head_value
        value = head_value("長" * 500)
        self.assertTrue(value.endswith("&#8230;"))
        self.assertEqual(value.count("&#38263;"), 120)
