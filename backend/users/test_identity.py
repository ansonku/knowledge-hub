import re
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
)
from allauth.socialaccount.models import SocialAccount, SocialToken
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.views import OAuth2Adapter
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .lifecycle import revoke_sessions
from .models import AuditLog, User
from .security import mfa_cipher, recovery_verifier

PASSWORD = "sable-track-trout-acorn-flowers"
NEW_PASSWORD = "bottle-jigsaw-branch-parcel-8080"
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def path_from_last_email():
    return urlsplit(re.search(r"https?://\S+", mail.outbox[-1].body).group()).path


def current_totp(secret):
    return format_hotp_value(hotp_value(secret, int(time.time()) // 30))


@override_settings(PASSWORD_HASHERS=FAST_HASHERS, ALLAUTH_TRUSTED_CLIENT_IP_HEADER=None)
class AccountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = self.make_user("admin", User.Role.ADMIN)
        self.viewer = self.make_user("reader")

    def make_user(self, name, role=User.Role.VIEWER):
        user = User.objects.create_user(name, f"{name}@example.test", PASSWORD, role=role)
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        return user

    def login(self, user, client=None, password=PASSWORD):
        return (client or self.client).post(reverse("account_login"), {"login": user.email, "password": password})

    def reauthenticate_admin(self):
        self.assertRedirects(self.login(self.admin), reverse("profile"))
        self.client.post(reverse("account_reauthenticate"), {"password": PASSWORD})

    def invite(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("manage_users"), {
                "username": "invited", "email": "Invite@EXAMPLE.test", "role": User.Role.EDITOR,
            })
        self.assertRedirects(response, reverse("manage_users"))
        return User.objects.get(username="invited"), path_from_last_email()

    def test_invitation_resend_expiry_activation_and_replay(self):
        self.reauthenticate_admin()
        user, old_path = self.invite()
        self.assertEqual(user.email, "invite@example.test")
        self.assertTrue(user.pending_activation)
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.login(user, Client()).status_code, 200)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("manage_user", args=[user.pk]), {"action": "resend"})
        self.assertEqual(response.status_code, 302)
        path = path_from_last_email()
        visitor = Client()
        self.assertEqual(visitor.get(old_path).status_code, 400)
        with patch("django.core.signing.time.time", return_value=time.time() + timedelta(hours=25).total_seconds()):
            self.assertEqual(visitor.get(path).status_code, 400)
        form_url = reverse("activation_form", args=[user.pk])
        self.assertRedirects(visitor.get(path), form_url)
        response = visitor.post(form_url, {"new_password1": PASSWORD, "new_password2": PASSWORD})
        self.assertRedirects(response, reverse("account_login"))
        self.assertEqual(visitor.get(path).status_code, 400)
        self.assertRedirects(self.login(user, visitor), reverse("profile"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.pending_activation)
        self.assertTrue(EmailAddress.objects.filter(user=user, verified=True).exists())

    def test_roles_public_signup_and_csrf(self):
        response = self.client.post(reverse("account_signup"), {"email": "public@example.test", "password1": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="public@example.test").exists())
        for role in (User.Role.VIEWER, User.Role.EDITOR):
            with self.subTest(role=role):
                self.viewer.role = role
                self.viewer.save(update_fields=["role"])
                self.client.force_login(self.viewer)
                self.assertEqual(self.client.get(reverse("manage_users")).status_code, 403)
                self.assertEqual(self.client.get(reverse("users_api")).status_code, 403)
                self.assertEqual(self.client.post(reverse("manage_users"), {}).status_code, 403)
                self.assertEqual(self.client.get(reverse("auth_me")).json()["role"], role)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("users_api")).status_code, 200)
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.login(self.admin, csrf_client).status_code, 403)
        csrf_client.get(reverse("account_login"))
        token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(csrf_client.post(reverse("account_login"), {
            "login": self.admin.email, "password": PASSWORD, "csrfmiddlewaretoken": token,
        }).status_code, 302)
        self.assertEqual(csrf_client.post(reverse("profile"), {"display_name": "Blocked"}).status_code, 403)

    def test_vue_account_management_reads_and_submits_as_admin(self):
        browser = Client(enforce_csrf_checks=True)
        detail_url = reverse("user_api", args=[self.viewer.pk])
        browser.force_login(self.viewer)
        self.assertEqual(browser.get(detail_url).status_code, 403)

        self.reauthenticate_admin()
        session_cookie = self.client.cookies["sessionid"].value
        browser.cookies["sessionid"] = session_cookie
        accounts = browser.get(reverse("users_api")).json()
        self.assertEqual(accounts["count"], 2)
        self.assertEqual(accounts["page_count"], 1)
        self.assertEqual(browser.get(detail_url).json()["account"]["role"], User.Role.VIEWER)
        with self.captureOnCommitCallbacks(execute=True):
            response = browser.post(reverse("manage_users"), {
                "username": "new-reader", "email": "new-reader@example.test",
                "role": User.Role.VIEWER, "csrfmiddlewaretoken": accounts["csrf_token"],
            })
        self.assertRedirects(response, reverse("manage_users"), fetch_redirect_response=False)
        account = User.objects.get(username="new-reader")
        detail = browser.get(reverse("user_api", args=[account.pk])).json()
        self.assertTrue(detail["account"]["pending_activation"])
        self.assertEqual(detail["audit"][0]["action"], "invited")
        self.assertTrue(detail["notices"])

    def test_vue_profile_update_requires_session_and_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        url = reverse("auth_me")
        self.assertEqual(browser.get(url).status_code, 403)
        browser.force_login(self.viewer)
        profile = browser.get(url).json()
        self.assertIn("csrftoken", browser.cookies)
        self.assertEqual(browser.patch(url, {"display_name": "Anson"}, content_type="application/json").status_code, 403)
        response = browser.patch(
            url, {"display_name": "Anson", "role": "admin"}, content_type="application/json",
            headers={"X-CSRFToken": profile["csrf_token"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "Anson")
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.role, User.Role.VIEWER)
        self.assertTrue(AuditLog.objects.filter(target=self.viewer, action="display_name_changed").exists())

    def test_disable_revokes_session_even_after_reenable(self):
        browser = Client()
        self.login(self.viewer, browser)
        self.reauthenticate_admin()
        url = reverse("manage_user", args=[self.viewer.pk])
        self.assertEqual(self.client.post(url, {"action": "disable"}).status_code, 302)
        disabled_browser = Client()
        self.assertRedirects(self.login(self.viewer, disabled_browser), reverse("account_inactive"))
        self.assertEqual(disabled_browser.get(reverse("auth_me")).status_code, 403)
        self.assertEqual(self.client.post(url, {"action": "enable"}).status_code, 302)
        self.assertEqual(browser.get(reverse("auth_me")).status_code, 403)
        self.assertRedirects(self.login(self.viewer, browser), reverse("profile"))

    def enable_mfa(self, user):
        secret = generate_totp_secret()
        return Authenticator.objects.create(
            user=user, type=Authenticator.Type.TOTP, data={
                "secret": mfa_cipher().encrypt(secret.encode()).decode(),
                "recovery_verifiers": [recovery_verifier("safe-recovery-code")],
            },
        )

    def test_totp_enrollment_recovery_replay_and_revocation(self):
        old_session = Client()
        self.login(self.viewer, old_session)
        self.login(self.viewer)
        self.client.post(reverse("account_reauthenticate"), {"password": PASSWORD})
        enable = reverse("mfa_activate_totp")
        self.assertEqual(self.client.get(enable).status_code, 200)
        encrypted = self.client.session[SECRET_SESSION_KEY]
        secret = mfa_cipher().decrypt(encrypted.encode()).decode()
        response = self.client.post(enable, {"code": current_totp(secret)})
        self.assertEqual(response.status_code, 200)
        codes = response.context["codes"]
        self.assertEqual(len(set(codes)), 10)
        row = Authenticator.objects.get(user=self.viewer)
        self.assertNotEqual(row.data["secret"], secret)
        self.assertEqual(row.data["recovery_verifiers"], [recovery_verifier(code) for code in codes])
        self.assertEqual(old_session.get(reverse("auth_me")).status_code, 403)
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("mfa_index")), codes[0])

        challenge = reverse("mfa_authenticate")
        pending = Client()
        self.assertRedirects(self.login(self.viewer, pending), challenge)
        self.assertEqual(pending.get(reverse("auth_me")).status_code, 403)
        self.assertRedirects(pending.post(challenge, {"code": codes[0]}), reverse("profile"))
        retry = Client()
        self.assertRedirects(self.login(self.viewer, retry), challenge)
        self.assertEqual(retry.post(challenge, {"code": codes[0]}).status_code, 200)
        self.assertEqual(retry.get(reverse("auth_me")).status_code, 403)
        self.assertRedirects(retry.post(challenge, {"code": current_totp(secret)}), reverse("profile"))

    def test_password_reset_does_not_grant_session_or_bypass_mfa(self):
        self.enable_mfa(self.viewer)
        old_login = Client()
        challenge = reverse("mfa_authenticate")
        self.assertRedirects(self.login(self.viewer, old_login), challenge)

        self.client.post(reverse("account_reset_password"), {"email": self.viewer.email})
        reset_url = path_from_last_email()
        response = self.client.get(reset_url)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
        self.assertRedirects(response, reverse("account_reset_password_from_key_done"))
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 403)
        self.assertRedirects(old_login.post(challenge, {"code": "safe-recovery-code"}), reverse("account_login"))
        self.assertRedirects(self.login(self.viewer, password=NEW_PASSWORD), challenge)
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 403)
        self.assertEqual(self.client.get(reset_url).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(target=self.viewer, action="password_reset").exists())

    @override_settings(ACCOUNT_RATE_LIMITS={"login_failed": "2/m/key"})
    def test_mfa_rate_limit_blocks_further_guesses(self):
        self.enable_mfa(self.viewer)
        challenge = reverse("mfa_authenticate")
        self.assertRedirects(self.login(self.viewer), challenge)
        for _ in range(2):
            self.assertEqual(self.client.post(challenge, {"code": "incorrect"}).status_code, 200)
        self.assertEqual(self.client.post(challenge, {"code": "safe-recovery-code"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 403)

    def test_admin_mfa_reset_requires_verification_and_audits(self):
        self.enable_mfa(self.viewer)
        pending = Client()
        self.login(self.viewer, pending)
        self.reauthenticate_admin()
        url = reverse("manage_user", args=[self.viewer.pk])
        self.assertEqual(self.client.post(url, {"action": "mfa", "reason": "Help desk"}).status_code, 200)
        self.assertTrue(Authenticator.objects.filter(user=self.viewer).exists())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"action": "mfa", "reason": "In-person check", "verified": "on"})
        self.assertRedirects(response, url)
        self.assertFalse(Authenticator.objects.filter(user=self.viewer).exists())
        log = AuditLog.objects.get(target=self.viewer, action="mfa_admin_reset")
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual(log.metadata, {"reason": "In-person check", "identity_verified": True})
        self.assertEqual(mail.outbox[-1].to, [self.viewer.email])
        self.assertRedirects(pending.get(reverse("mfa_authenticate")), reverse("account_login"))
        self.assertEqual(pending.get(reverse("auth_me")).status_code, 403)


@override_settings(
    PASSWORD_HASHERS=FAST_HASHERS,
    ALLAUTH_TRUSTED_CLIENT_IP_HEADER=None,
    GOOGLE_CONFIGURED=True,
    SOCIALACCOUNT_PROVIDERS={
        "google": {"OAUTH_PKCE_ENABLED": True, "APPS": [{"client_id": "test-client", "secret": "test-secret"}]},
    },
)
class GoogleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("reader", "reader@example.test", PASSWORD)
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)

    def callback(self, browser, redirect_response, subject="google-subject", email=None):
        query = parse_qs(urlsplit(redirect_response.url).query)
        self.assertIn("code_challenge", query)
        response = {"access_token": "fixture-oauth-token", "id_token": "mocked-id-token"}
        claims = {"sub": subject, "email": email or self.user.email, "email_verified": True}
        with (
            patch.object(OAuth2Adapter, "get_access_token_data", return_value=response) as exchange,
            patch.object(GoogleOAuth2Adapter, "_decode_id_token", return_value=claims),
        ):
            result = browser.get(reverse("google_callback"), {"state": query["state"][0], "code": "fixture-code"})
        self.assertTrue(exchange.call_args.kwargs["pkce_code_verifier"])
        return result

    def login(self, browser):
        return browser.post(reverse("account_login"), {"login": self.user.email, "password": PASSWORD})

    def test_unlinked_google_does_not_create_or_email_link(self):
        for email in (self.user.email, "unknown@example.test"):
            with self.subTest(email=email):
                start = self.client.post(reverse("google_login"))
                self.callback(self.client, start, email=email)
                self.assertEqual(self.client.get(reverse("auth_me")).status_code, 403)
                self.assertFalse(SocialAccount.objects.exists())
                self.assertEqual(User.objects.count(), 1)

    def test_google_link_requires_profile_and_fresh_factor(self):
        link = reverse("google_connect")
        self.assertRedirects(self.client.get(link), f"{reverse('account_login')}?next={link}")
        self.login(self.client)
        start = self.client.post(reverse("google_login") + "?process=connect", {"process": "connect"})
        self.callback(self.client, start)
        self.assertFalse(SocialAccount.objects.exists())

        response = self.client.post(link)
        self.assertTrue(response.url.startswith(reverse("account_reauthenticate")))
        self.assertFalse(SocialAccount.objects.exists())
        next_url = parse_qs(urlsplit(response.url).query)["next"][0]
        response = self.client.post(reverse("account_reauthenticate"), {"password": PASSWORD, "next": next_url})
        self.assertRedirects(self.callback(self.client, response), reverse("socialaccount_connections"))
        self.assertEqual(SocialAccount.objects.get(provider="google").uid, "google-subject")
        self.assertFalse(SocialToken.objects.exists())
        self.assertTrue(AuditLog.objects.filter(target=self.user, action="google_linked").exists())

    def test_linked_google_needs_mfa_and_disabled_account_is_blocked(self):
        SocialAccount.objects.create(user=self.user, provider="google", uid="google-subject")
        secret = generate_totp_secret()
        Authenticator.objects.create(user=self.user, type=Authenticator.Type.TOTP, data={
            "secret": mfa_cipher().encrypt(secret.encode()).decode(),
        })
        challenge = reverse("mfa_authenticate")
        response = self.callback(self.client, self.client.post(reverse("google_login")), email="renamed@example.test")
        self.assertRedirects(response, challenge)
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 403)
        self.assertNotIn("fixture-oauth-token", str(dict(self.client.session)))
        self.assertRedirects(self.client.post(challenge, {"code": current_totp(secret)}), reverse("profile"))
        self.assertEqual(self.client.get(reverse("auth_me")).status_code, 200)

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        revoke_sessions(self.user)
        browser = Client()
        self.callback(browser, browser.post(reverse("google_login")))
        self.assertEqual(browser.get(reverse("auth_me")).status_code, 403)
