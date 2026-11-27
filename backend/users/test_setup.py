"""P24: first-run setup — opening, the hour, the setup code, finishing, and closing for good."""
import io
import os
import stat
import tempfile
from datetime import timedelta
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from hub import about

from . import setup
from .models import AuditLog, SetupState, User

PASSWORD = "Correct-Horse-42"


def admin_form(**changes):
    form = {"display_name": "Taiwan", "username": "hub.tw", "email": "hub@example.test", "password": PASSWORD}
    form.update(changes)
    return {"terms_version": about.TERMS_VERSION, "admin": form}


def allow_without_mfa():
    from documents.models import SiteSettings
    SiteSettings.objects.filter(pk=1).update(require_admin_mfa=False)


class SetupTestCase(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        storage = override_settings(DOCUMENT_STORAGE=folder.name)
        storage.enable()
        self.addCleanup(storage.disable)
        setup.reset_cache()
        self.addCleanup(setup.reset_cache)
        cache.clear()

    def open(self, ago=timedelta(0)):
        """Open setup as prepare_setup would, `ago` in the past; returns the code from the file."""
        call_command("prepare_setup", stdout=io.StringIO())
        if ago:
            SetupState.objects.filter(pk=1).update(opened_at=timezone.now() - ago)
        return setup.code_file().read_text().strip()

    def post(self, path, data, client=None):
        return (client or self.client).post(path, data, content_type="application/json")


class OpeningTests(SetupTestCase):
    def test_without_a_setup_row_nothing_changes(self):
        self.assertEqual(self.client.get("/api/setup/").json(), {"required": False})
        self.assertNotEqual(self.client.get("/api/documents/").status_code, 503)

    def test_prepare_setup_writes_a_private_code_file_and_never_prints_the_code(self):
        output = io.StringIO()
        call_command("prepare_setup", stdout=output)
        code = setup.code_file().read_text().strip()
        self.assertRegex(code, r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")
        self.assertEqual(stat.S_IMODE(os.stat(setup.code_file()).st_mode), 0o600)
        self.assertNotIn(code, output.getvalue())
        self.assertNotIn(code.replace("-", ""), output.getvalue())
        self.assertIn(str(setup.code_file()), output.getvalue())
        state = SetupState.objects.get(pk=1)
        self.assertNotIn(code.replace("-", ""), state.code_hash)

    def test_restarting_opens_a_new_hour_with_a_new_code(self):
        first = self.open(ago=timedelta(hours=2))
        second = self.open()
        self.assertNotEqual(first, second)
        self.assertGreater(self.client.get("/api/setup/").json()["window_seconds"], 3500)

    def test_with_an_admin_prepare_setup_closes_it(self):
        self.open()
        User.objects.create_user("boss", "boss@example.test", role=User.Role.ADMIN)
        call_command("prepare_setup", stdout=io.StringIO())
        self.assertFalse(setup.code_file().exists())
        self.assertIsNotNone(SetupState.objects.get(pk=1).completed_at)
        setup.reset_cache()
        self.assertEqual(self.client.get("/api/setup/").json(), {"required": False})


class PendingTests(SetupTestCase):
    def test_pages_go_to_setup_and_the_api_answers_503(self):
        self.open()
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["setup_required"])
        self.assertEqual(self.client.get("/api/public/articles/").status_code, 503)
        for path in ("/", "/accounts/login/", "/articles/"):
            response = self.client.get(path)
            self.assertEqual((response.status_code, response["Location"]), (302, "/setup/"), path)
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_status_within_the_hour(self):
        self.open()
        found = self.client.get("/api/setup/").json()
        self.assertTrue(found["required"])
        self.assertFalse(found["code_required"])
        self.assertGreater(found["window_seconds"], 3500)
        self.assertEqual(found["about"]["developer"]["email"], "ansonku@gmail.com")
        self.assertEqual([part["title"] for part in found["about"]["terms"]][0], "1. 部署與資料")
        self.assertIn("smtp", found["checks"])
        self.assertNotIn("code_hash", str(found))


class FinishingTests(SetupTestCase):
    def test_within_the_hour_no_code_is_needed(self):
        self.open()
        self.assertTrue(self.post("/api/setup/verify", {}).json()["permitted"])
        response = self.post("/api/setup/complete", {
            **admin_form(), "site": {"name": "台灣知識庫", "tagline": "測試介紹", "storage_limit_gb": 100},
        })
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(username="hub.tw")
        self.assertEqual((user.role, user.display_name, user.is_active), (User.Role.ADMIN, "Taiwan", True))
        self.assertTrue(EmailAddress.objects.get(user=user).verified)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "admin")
        row = AuditLog.objects.get(action="admin_bootstrapped")
        self.assertEqual(row.metadata, {"via": "setup", "terms_version": about.TERMS_VERSION})
        from documents.models import SiteSettings
        site = SiteSettings.current()
        self.assertEqual((site.name, site.tagline, site.storage_limit), ("台灣知識庫", "測試介紹", 100 * 1024 ** 3))
        self.assertFalse(setup.code_file().exists())
        self.assertIsNotNone(SetupState.objects.get(pk=1).completed_at)
        self.assertNotEqual(self.client.get("/api/documents/").status_code, 503)
        self.assertEqual(self.post("/api/setup/complete", admin_form(username="again", email="again@example.test")).status_code, 410)
        self.assertEqual(self.client.get("/api/setup/").json(), {"required": False})

    def test_site_settings_are_optional(self):
        self.open()
        self.post("/api/setup/verify", {})
        self.assertEqual(self.post("/api/setup/complete", admin_form()).status_code, 201)

    def test_completing_needs_a_permit(self):
        self.open()
        response = self.post("/api/setup/complete", admin_form())
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["permit_expired"])
        self.assertFalse(User.objects.exists())

    def test_the_permit_lasts_thirty_minutes(self):
        self.open()
        self.post("/api/setup/verify", {})
        later = timezone.now() + timedelta(minutes=31)
        with patch("users.setup.timezone.now", return_value=later):
            self.assertEqual(self.post("/api/setup/complete", admin_form()).status_code, 403)

    def test_password_rules_terms_and_duplicates(self):
        self.open()
        self.post("/api/setup/verify", {})
        for form, field in ((admin_form(password="short"), "password"), (admin_form(password="hub.tw.hub"), "password"),
                            (admin_form(email="not-an-email"), "admin")):
            response = self.post("/api/setup/complete", form)
            self.assertEqual(response.status_code, 400, form)
        stale = {**admin_form(), "terms_version": about.TERMS_VERSION + 1}
        self.assertIn("terms_version", self.post("/api/setup/complete", stale).json())
        self.assertFalse(User.objects.exists())


class CodeTests(SetupTestCase):
    def test_after_the_hour_the_code_is_needed(self):
        code = self.open(ago=timedelta(hours=1, minutes=1))
        found = self.client.get("/api/setup/").json()
        self.assertTrue(found["code_required"])
        self.assertEqual(found["window_seconds"], 0)
        wrong = self.post("/api/setup/verify", {"code": "AAAA-AAAA-AAAA"})
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("還可以再試 4 次", str(wrong.json()["code"]))
        self.assertEqual(self.post("/api/setup/complete", admin_form()).status_code, 403)
        # Lower case and without dashes is fine.
        self.assertTrue(self.post("/api/setup/verify", {"code": code.replace("-", "").lower()}).json()["permitted"])
        self.assertEqual(self.post("/api/setup/complete", admin_form()).status_code, 201)

    def test_five_wrong_codes_pause_this_client(self):
        code = self.open(ago=timedelta(hours=2))
        with self.assertLogs("users.setup", "WARNING"):
            for _ in range(5):
                self.post("/api/setup/verify", {"code": "BBBB-BBBB-BBBB"})
        response = self.post("/api/setup/verify", {"code": code})
        self.assertEqual(response.status_code, 429)
        self.assertIn("10 分鐘", response.json()["detail"])

    def test_the_code_never_reaches_the_logs(self):
        code = self.open(ago=timedelta(hours=2))
        with self.assertLogs("users.setup", "DEBUG") as logs:
            self.post("/api/setup/verify", {"code": "CCCC-CCCC-CCCC"})
            self.post("/api/setup/verify", {"code": code})
            self.post("/api/setup/complete", admin_form())
        joined = "\n".join(logs.output)
        self.assertNotIn(code, joined)
        self.assertNotIn(code.replace("-", ""), joined)
        self.assertNotIn(PASSWORD, joined)


class CommandTests(SetupTestCase):
    def test_create_hub_admin_also_closes_setup(self):
        self.open()
        with patch("users.management.commands.create_hub_admin.getpass", return_value=PASSWORD):
            call_command("create_hub_admin", "boss", "boss@example.test", stdout=io.StringIO())
        self.assertFalse(setup.code_file().exists())
        setup.reset_cache()
        self.assertEqual(self.client.get("/api/setup/").json(), {"required": False})
        self.assertEqual(AuditLog.objects.get(action="admin_bootstrapped").metadata, {"via": "command"})

    def test_two_finishes_at_once_make_one_admin(self):
        self.open()
        other = self.client_class()
        for client in (self.client, other):
            self.post("/api/setup/verify", {}, client)
        self.assertEqual(self.post("/api/setup/complete", admin_form(), self.client).status_code, 201)
        late = self.post("/api/setup/complete", admin_form(username="second", email="second@example.test"), other)
        self.assertEqual(late.status_code, 410)
        self.assertEqual(User.objects.filter(role=User.Role.ADMIN).count(), 1)



class OnboardingTests(SetupTestCase):
    """P24c: the About page and the getting-started card."""

    def test_about_lists_who_accepted_which_terms(self):
        self.open()
        self.post("/api/setup/verify", {})
        self.post("/api/setup/complete", admin_form())
        # P25: the wizard's site requires admin two-factor; this admin has none yet.
        blocked = self.client.get("/api/admin/about/")
        self.assertEqual(blocked.status_code, 403)
        self.assertTrue(blocked.json()["mfa_required"])
        allow_without_mfa()
        found = self.client.get("/api/admin/about/").json()
        self.assertEqual(found["developer"]["github"], "https://github.com/ansonku/knowledge-hub")
        self.assertEqual(found["license"], "")
        self.assertEqual(found["accepted"][0]["by"], "Taiwan")
        self.assertEqual((found["accepted"][0]["via"], found["accepted"][0]["terms_version"]), ("setup", about.TERMS_VERSION))

    def test_getting_started_follows_the_data(self):
        self.open()
        self.post("/api/setup/verify", {})
        self.post("/api/setup/complete", admin_form())
        allow_without_mfa()
        found = self.client.get("/api/admin/getting-started/").json()
        self.assertEqual(found["tasks"], {"admin": True, "members": False, "collections": False, "documents": False, "mfa": False})
        self.assertEqual((found["done"], found["total"]), (1, 5))
        from documents.models import Category
        Category.objects.create(name="操作指南")
        User.objects.create_user("reader", "reader@example.test")
        found = self.client.get("/api/admin/getting-started/").json()
        self.assertTrue(found["tasks"]["collections"] and found["tasks"]["members"])
        self.assertEqual(found["done"], 3)

    def test_only_admins(self):
        editor = User.objects.create_user("editor", "editor@example.test", role=User.Role.EDITOR)
        self.client.force_login(editor)
        self.assertEqual(self.client.get("/api/admin/about/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/getting-started/").status_code, 403)
