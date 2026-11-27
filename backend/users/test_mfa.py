"""P25: recovery codes, regenerating them, trusting a browser for 10 days, requiring two-factor for admins, and
the reset_hub_mfa command."""
import io
from unittest.mock import patch

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from documents.models import Category, SiteSettings, Tag

from .lifecycle import revoke_sessions
from .mfa import issue_recovery_codes, normalized
from .models import AuditLog, User
from .security import mfa_cipher, recovery_verifier
from .test_identity import FAST_HASHERS, PASSWORD, current_totp, past_trust


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, ALLAUTH_TRUSTED_CLIENT_IP_HEADER=None)
class MfaTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("boss", "boss@example.test", PASSWORD, role=User.Role.ADMIN)
        self.viewer = User.objects.create_user("reader", "reader@example.test", PASSWORD)
        self.editor = User.objects.create_user("writer", "writer@example.test", PASSWORD, role=User.Role.EDITOR)

    def enable(self, user, legacy=None):
        secret = generate_totp_secret()
        auth = Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={
            "secret": mfa_cipher().encrypt(secret.encode()).decode(),
            "recovery_verifiers": [recovery_verifier(legacy)] if legacy else [],
        })
        return auth, secret

    def login(self, user, client):
        return client.post(reverse("account_login"), {"login": user.email, "password": PASSWORD})

    def sign_in(self, user, code, client=None, trust=False):
        client = client or Client()
        self.assertRedirects(self.login(user, client), reverse("mfa_authenticate"))
        response = client.post(reverse("mfa_authenticate"), {"code": code, **({"trust": "on"} if trust else {})})
        return client, past_trust(client, response)


class RecoveryCodeTests(MfaTestCase):
    def test_new_codes_look_like_7Q4M_2KXD_and_work_once_in_any_case(self):
        auth, _ = self.enable(self.viewer)
        codes = issue_recovery_codes(auth)
        self.assertEqual(len(set(codes)), 10)
        for code in codes:
            self.assertRegex(code, r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")
        typed = codes[0].replace("-", "").lower()
        client, response = self.sign_in(self.viewer, typed)
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)
        auth.refresh_from_db()
        self.assertEqual(len(auth.data["recovery_verifiers"]), 9)
        retry = Client()
        self.login(self.viewer, retry)
        self.assertEqual(retry.post(reverse("mfa_authenticate"), {"code": codes[0]}).status_code, 200)  # used up

    def test_older_twenty_character_codes_still_work(self):
        self.enable(self.viewer, legacy="9a57fac207d3cc92e180")
        _, response = self.sign_in(self.viewer, "9a57fac207d3cc92e180")
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)

    def test_normalising(self):
        self.assertEqual(normalized(" 7q4m-2kxd "), "7Q4M2KXD")

    def test_regenerating_needs_a_recent_sign_in_and_replaces_the_old_set(self):
        auth, secret = self.enable(self.viewer)
        old = issue_recovery_codes(auth)
        client, _ = self.sign_in(self.viewer, old[0])  # a recovery code, so the TOTP code below is fresh
        page = client.get(reverse("mfa_regenerate_recovery"))
        before = client.post(reverse("mfa_regenerate_recovery"))
        self.assertIn("reauthenticate", before["Location"])  # confirm who you are first
        client.post(reverse("mfa_reauthenticate"), {"code": current_totp(secret)})
        self.assertContains(page, "10")  # codes left before regenerating
        response = client.post(reverse("mfa_regenerate_recovery"))
        self.assertEqual(response.status_code, 200)
        new = response.context["codes"]
        self.assertTrue(set(new).isdisjoint(old))
        auth.refresh_from_db()
        self.assertEqual(auth.data["recovery_verifiers"], [recovery_verifier(normalized(code)) for code in new])
        self.assertTrue(AuditLog.objects.filter(action="mfa_recovery_regenerated", target=self.viewer).exists())
        # Later on, regenerating asks to confirm who you are again.
        with patch("allauth.account.internal.flows.reauthentication.did_recently_reauthenticate", return_value=False), \
                patch("allauth.account.decorators.did_recently_reauthenticate", return_value=False, create=True):
            stale = client.post(reverse("mfa_regenerate_recovery"))
        self.assertEqual(stale.status_code, 302)
        self.assertIn("reauthenticate", stale["Location"])

    def test_me_reports_status_but_never_codes(self):
        auth, _ = self.enable(self.viewer)
        codes = issue_recovery_codes(auth)
        client = Client()
        client.force_login(self.viewer)
        found = client.get("/api/auth/me").json()
        self.assertEqual(found["mfa"], {"enabled": True, "recovery_codes": 10, "required": False})
        self.assertNotIn(codes[0], str(found))
        other = Client()
        other.force_login(self.editor)
        self.assertEqual(other.get("/api/auth/me").json()["mfa"], {"enabled": False, "recovery_codes": None, "required": False})


class TrustTests(MfaTestCase):
    def test_ten_days_without_asking_when_ticked(self):
        auth, _ = self.enable(self.viewer)
        codes = issue_recovery_codes(auth)
        client, response = self.sign_in(self.viewer, codes[0], trust=True)
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)
        cookie = client.cookies["mfa_trusted"]
        self.assertEqual(int(cookie["max-age"]), 10 * 24 * 3600)
        client.post(reverse("account_logout"))
        self.assertRedirects(self.login(self.viewer, client), "/app/", fetch_redirect_response=False)

    def test_not_ticked_means_no_trust(self):
        auth, _ = self.enable(self.viewer)
        codes = issue_recovery_codes(auth)
        client, _ = self.sign_in(self.viewer, codes[0])
        self.assertNotIn("mfa_trusted", client.cookies)

    def test_signing_out_everywhere_or_a_new_password_ends_trust(self):
        auth, _ = self.enable(self.viewer)
        codes = issue_recovery_codes(auth)
        client, _ = self.sign_in(self.viewer, codes[0], trust=True)
        client.post(reverse("account_logout"))
        revoke_sessions(self.viewer)
        self.assertRedirects(self.login(self.viewer, client), reverse("mfa_authenticate"))
        # Trust again, then change the password.
        trusted = Client()
        trusted, _ = self.sign_in(self.viewer, codes[1], client=trusted, trust=True)
        trusted.post(reverse("account_logout"))
        self.viewer.refresh_from_db()
        self.viewer.set_password(PASSWORD)  # a new hash, even for the same password
        self.viewer.save()
        self.assertRedirects(self.login(self.viewer, trusted), reverse("mfa_authenticate"))


class RequiredForAdminsTests(MfaTestCase):
    def require(self, on=True):
        SiteSettings.objects.update_or_create(pk=1, defaults={"require_admin_mfa": on})

    def test_admins_without_two_factor_are_held_back_from_admin_apis_only(self):
        self.require()
        client = Client()
        client.force_login(self.admin)
        response = client.get("/api/admin/system/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["mfa_required"])
        self.assertEqual(client.get("/api/documents/").status_code, 200)  # the workspace keeps working
        self.assertTrue(client.get("/api/auth/me").json()["mfa"]["required"])
        # Inline admin checks too: merging tags.
        first, second = Tag.objects.create(name="a"), Tag.objects.create(name="b")
        merged = client.post("/api/tags/merge/", {"sources": [first.pk], "target": second.pk}, content_type="application/json")
        self.assertEqual(merged.status_code, 403, merged.content)
        self.assertTrue(merged.json().get("mfa_required"), merged.content)

    def test_with_two_factor_or_when_off_admins_carry_on(self):
        self.require()
        self.enable(self.admin)
        client = Client()
        client.force_login(self.admin)
        self.assertEqual(client.get("/api/admin/system/").status_code, 200)
        self.require(False)
        plain = User.objects.create_user("boss2", "boss2@example.test", PASSWORD, role=User.Role.ADMIN)
        other = Client()
        other.force_login(plain)
        self.assertEqual(other.get("/api/admin/system/").status_code, 200)

    def test_editors_and_viewers_are_unaffected(self):
        self.require()
        client = Client()
        client.force_login(self.editor)
        self.assertEqual(client.get("/api/categories/").status_code, 200)
        Category.objects.create(name="集合")
        self.assertFalse(client.get("/api/auth/me").json()["mfa"]["required"])

    def test_the_setting_needs_your_own_two_factor_first_and_is_audited(self):
        client = Client()
        client.force_login(self.admin)
        refused = client.put("/api/admin/security/", {"require_admin_mfa": True}, content_type="application/json")
        self.assertEqual(refused.status_code, 400)
        self.enable(self.admin)
        found = client.put("/api/admin/security/", {"require_admin_mfa": True}, content_type="application/json").json()
        self.assertEqual(found, {"require_admin_mfa": True, "admins": 1, "admins_without_mfa": 0})
        self.assertTrue(AuditLog.objects.filter(action="site_security_updated").exists())
        editor = Client()
        editor.force_login(self.editor)
        self.assertEqual(editor.get("/api/admin/security/").status_code, 403)


class ResetCommandTests(MfaTestCase):
    def test_reset_hub_mfa(self):
        self.enable(self.admin)
        version = self.admin.session_version
        output = io.StringIO()
        call_command("reset_hub_mfa", "BOSS@example.test", reason="驗證過身分證件", stdout=output)
        self.assertFalse(Authenticator.objects.filter(user=self.admin).exists())
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.session_version, version + 1)
        row = AuditLog.objects.get(action="mfa_command_reset")
        self.assertEqual(row.metadata, {"reason": "驗證過身分證件"})
        with self.assertRaises(CommandError):
            call_command("reset_hub_mfa", "boss@example.test", reason="再一次", stdout=io.StringIO())  # nothing to reset
        with self.assertRaises(CommandError):
            call_command("reset_hub_mfa", "nobody@example.test", reason="不存在的人", stdout=io.StringIO())
