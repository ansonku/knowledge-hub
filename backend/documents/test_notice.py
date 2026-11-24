from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from users.models import AuditLog, User

from .models import SiteSettings

URL = "/api/site/notice/"


class NoticeTests(TestCase):
    """P6c: the announcement banner."""

    def setUp(self):
        self.admin = User.objects.create_user("admin", "admin@example.test", role=User.Role.ADMIN)
        self.editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(self.admin)

    def put(self, client=None, **changes):
        data = {"enabled": True, "text": "週日 20:00 系統維護", "link": "", "level": "warning", "starts_at": None, "ends_at": None, **changes}
        return (client or self.client).put(URL, data, content_type="application/json")

    def test_admin_only(self):
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(self.put(editor).status_code, 403)
        self.assertEqual(self.put(Client()).status_code, 403)
        self.assertIsNone(Client().get("/api/site/").json()["notice"])

    def test_visible_to_everyone_while_on_and_in_window(self):
        self.assertEqual(self.put().status_code, 200)
        visitor = Client().get("/api/site/").json()
        self.assertEqual({k: visitor["notice"][k] for k in ("text", "link", "level")}, {"text": "週日 20:00 系統維護", "link": "", "level": "warning"})
        self.assertNotIn("notice_settings", visitor)  # the stored settings are for Admins only
        self.assertIn("notice_settings", self.client.get("/api/site/").json())
        # Django pages get it through the context processor.
        self.assertContains(Client().get("/accounts/login/"), "週日 20:00 系統維護")

        now = timezone.now()
        self.put(starts_at=(now + timedelta(hours=1)).isoformat())
        self.assertIsNone(Client().get("/api/site/").json()["notice"])
        self.put(ends_at=(now - timedelta(minutes=1)).isoformat())
        self.assertIsNone(Client().get("/api/site/").json()["notice"])
        self.put(enabled=False)
        self.assertIsNone(Client().get("/api/site/").json()["notice"])
        self.assertNotContains(Client().get("/accounts/login/"), "週日 20:00 系統維護")

    def test_edits_change_the_id(self):
        self.put()
        first = Client().get("/api/site/").json()["notice"]["id"]
        self.put(text="改到週六")
        self.assertNotEqual(Client().get("/api/site/").json()["notice"]["id"], first)

    def test_validation(self):
        self.assertEqual(self.put(text="").status_code, 400)
        self.assertEqual(self.put(text="x" * 121).status_code, 400)
        self.assertEqual(self.put(level="loud").status_code, 400)
        for bad in ("javascript:alert(1)", "data:text/html,hi", "//evil.example/x", "ftp://example.com/", "/\\evil.example"):
            self.assertEqual(self.put(link=bad).status_code, 400, bad)
        now = timezone.now()
        self.assertEqual(self.put(starts_at=now.isoformat(), ends_at=(now - timedelta(hours=1)).isoformat()).status_code, 400)
        self.assertFalse(SiteSettings.current().notice_enabled)
        for good in ("https://example.com/status", "/articles/", ""):
            self.assertEqual(self.put(link=good).status_code, 200, good)
        # Markup stays text; line breaks collapse.
        self.put(text="<b>維護</b>\n明天")
        self.assertEqual(Client().get("/api/site/").json()["notice"]["text"], "<b>維護</b> 明天")
        self.assertNotContains(Client().get("/accounts/login/"), "<b>維護</b>")
        # Switching off with empty text is allowed.
        self.assertEqual(self.put(enabled=False, text="").status_code, 200)

    def test_audited(self):
        self.put()
        self.put(text="改")
        self.put(enabled=False)
        self.assertEqual(list(AuditLog.objects.filter(action__startswith="site_notice").order_by("pk").values_list("action", flat=True)),
                         ["site_notice_enabled", "site_notice_updated", "site_notice_disabled"])
