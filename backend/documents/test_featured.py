from datetime import timedelta

from django.test import Client
from django.utils import timezone

from .models import ArticleViewDaily, Document, DocumentActivity, FeaturedArticle
from .test_popularity import PopularityFixture

URL = "/api/admin/featured/"


class FeaturedTests(PopularityFixture):
    """P6b: Admins pin up to four published articles; popular skips them."""

    def put(self, ids, client=None):
        return (client or self.client).put(URL, {"documents": [str(pk) for pk in ids]}, content_type="application/json")

    def test_admin_only(self):
        first = self.article("First")
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(self.put([first], editor).status_code, 403)
        self.assertEqual(editor.get(URL).status_code, 403)
        self.assertEqual(self.put([first], self.visitor).status_code, 403)
        self.assertFalse(FeaturedArticle.objects.exists())

    def test_order_limits_and_public_list(self):
        a, b, c, d, e = (self.article(name) for name in "ABCDE")
        private = self.article("Private", publish=False)
        self.assertEqual(self.put([a, b, c, d, e]).status_code, 400)
        self.assertEqual(self.put([a, a]).status_code, 400)
        self.assertEqual(self.put([a, private]).status_code, 400)
        self.assertFalse(FeaturedArticle.objects.exists())

        response = self.put([c, a, b])
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["title"] for item in response.json()["results"]], ["C", "A", "B"])
        public = self.visitor.get("/api/public/featured/").json()["results"]
        self.assertEqual([card["title"] for card in public], ["C", "A", "B"])
        self.assertEqual(set(public[0]), {"path", "document_id", "title", "format", "published_at", "excerpt", "reading_minutes", "collection"})

        self.put([b, c])  # reorder and remove A
        self.assertEqual([card["title"] for card in self.visitor.get("/api/public/featured/").json()["results"]], ["B", "C"])
        actions = list(DocumentActivity.objects.filter(action__in=["featured", "unfeatured"]).values_list("document_id", "action"))
        self.assertEqual(sorted((str(pk), action) for pk, action in actions),
                         sorted([(c, "featured"), (a, "featured"), (b, "featured"), (a, "unfeatured")]))
        audit = self.client.get("/api/admin/audit/?category=publish").json()["results"]
        self.assertGreaterEqual(sum(1 for row in audit if row["action"] in ("featured", "unfeatured")), 4)

    def test_withdraw_and_trash_remove_for_good(self):
        a, b = self.article("A"), self.article("B")
        self.put([a, b])
        self.client.delete(f"/api/documents/{a}/publication/")
        self.client.delete(f"/api/documents/{b}/")
        self.assertFalse(FeaturedArticle.objects.exists())
        self.assertEqual(DocumentActivity.objects.filter(action="unfeatured", detail__automatic=True).count(), 2)
        # Republishing does not bring it back.
        version = Document.objects.get(pk=a).current_version_id
        self.client.post(f"/api/documents/{a}/publication/", {"version": str(version), "title": "A"}, content_type="application/json")
        self.assertEqual(self.visitor.get("/api/public/featured/").json()["results"], [])

    def test_popular_skips_featured_and_overview_marks_them(self):
        ids = [self.article(name) for name in ("One", "Two", "Three", "Four", "Five")]
        today = timezone.localdate()
        for rank, pk in enumerate(ids):
            ArticleViewDaily.objects.create(document_id=pk, day=today - timedelta(days=1), count=50 - rank)
        self.put([ids[0]])
        popular = [card["title"] for card in self.visitor.get("/api/public/popular/").json()["results"]]
        self.assertEqual(popular, ["Two", "Three", "Four", "Five"])
        overview = self.client.get("/api/admin/public-overview/").json()
        self.assertEqual(overview["featured"], [ids[0]])
        self.assertEqual([row["featured"] for row in overview["articles"]], [True, False, False, False, False])
        # Below three non-featured articles with views the section hides.
        self.put(ids[:3])
        self.assertEqual(self.visitor.get("/api/public/popular/").json(), {"results": []})
