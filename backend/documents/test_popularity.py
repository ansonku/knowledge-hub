import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from users.models import User

from .models import ArticleViewDaily, Document
from .popularity import ViewThrottle


class PopularityTests(TransactionTestCase):
    """P5e: anonymous view counting, popular articles and the Admin trend."""

    def setUp(self):
        cache.clear()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(DOCUMENT_STORAGE=str(Path(temporary.name)))
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(self.admin)
        self.visitor = Client()

    def article(self, title, publish=True):
        response = self.client.post("/api/documents/", {"file": SimpleUploadedFile("a.md", title.encode()), "title": title})
        document_id = response.json()["id"]
        if publish:
            version = Document.objects.get(pk=document_id).current_version_id
            self.client.post(f"/api/documents/{document_id}/publication/", {"version": str(version), "title": title},
                             content_type="application/json")
        return document_id

    def view(self, document_id, address="198.51.100.1"):
        return self.visitor.post(f"/api/public/articles/{document_id}/view/", headers={"X-Hub-Client-IP": address})

    def test_counts_published_articles_only_and_stores_no_visitor_data(self):
        published, private = self.article("Published"), self.article("Private", publish=False)
        self.assertEqual(self.view(published).status_code, 204)
        self.assertEqual(self.view(published, "203.0.113.9").status_code, 204)
        self.assertEqual(self.view(private).status_code, 404)
        self.assertEqual(self.visitor.get(f"/api/public/articles/{published}/view/").status_code, 405)
        row = ArticleViewDaily.objects.get(document_id=published)
        self.assertEqual((row.day, row.count), (timezone.localdate(), 2))
        self.assertFalse(ArticleViewDaily.objects.filter(document_id=private).exists())
        self.assertEqual({field.name for field in ArticleViewDaily._meta.get_fields()}, {"id", "document", "day", "count"})

    def test_rate_limited_per_client_address(self):
        published = self.article("Published")
        original = ViewThrottle.rate
        ViewThrottle.rate = "2/hour"
        self.addCleanup(setattr, ViewThrottle, "rate", original)
        self.assertEqual([self.view(published).status_code for _ in range(3)], [204, 204, 429])
        self.assertEqual(self.view(published, "203.0.113.50").status_code, 204)
        self.assertEqual(ArticleViewDaily.objects.get(document_id=published).count, 3)

    def test_popular_needs_three_articles_and_ranks_by_recent_views(self):
        first, second, third, old = (self.article(name) for name in ("First", "Second", "Third", "Old"))
        today = timezone.localdate()
        ArticleViewDaily.objects.create(document_id=first, day=today, count=5)
        ArticleViewDaily.objects.create(document_id=second, day=today, count=9)
        self.assertEqual(self.visitor.get("/api/public/popular/").json(), {"results": []})
        ArticleViewDaily.objects.create(document_id=third, day=today - timedelta(days=3), count=7)
        ArticleViewDaily.objects.create(document_id=old, day=today - timedelta(days=45), count=100)
        results = self.visitor.get("/api/public/popular/").json()["results"]
        self.assertEqual([card["title"] for card in results], ["Second", "Third", "First"])
        self.assertNotIn("count", str(results))
        # Withdrawn or trashed articles drop out (and the section hides again below the minimum).
        self.client.delete(f"/api/documents/{second}/publication/")
        self.assertEqual(self.visitor.get("/api/public/popular/").json(), {"results": []})

    def test_admin_trend(self):
        published = self.article("Published")
        today = timezone.localdate()
        ArticleViewDaily.objects.create(document_id=published, day=today, count=4)
        ArticleViewDaily.objects.create(document_id=published, day=today - timedelta(days=2), count=1)
        ArticleViewDaily.objects.create(document_id=published, day=today - timedelta(days=60), count=50)
        url = f"/api/documents/{published}/public-views/"
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(editor.get(url).status_code, 403)
        self.assertEqual(self.visitor.get(url).status_code, 403)
        trend = self.client.get(url).json()
        self.assertEqual(trend["total"], 5)
        self.assertEqual(len(trend["daily"]), 30)
        self.assertEqual(trend["daily"][-1], {"day": today.isoformat(), "count": 4})
