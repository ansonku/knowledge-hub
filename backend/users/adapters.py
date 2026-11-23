import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.internal.stagekit import clear_login
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.models import Authenticator
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthProcess
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import constant_time_compare

from .models import User
from .security import mfa_cipher

logger = logging.getLogger(__name__)

LOGIN_HASH = "hub_primary_login_hash"
GOOGLE_LINK_OWNER = "hub_google_link_owner"


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

    def pre_login(self, request, user, **kwargs):
        response = super().pre_login(request, user, **kwargs)
        if not response:
            request.session[LOGIN_HASH] = user.get_session_auth_hash()
        return response

    def login(self, request, user):
        expected = request.session.pop(LOGIN_HASH, "")
        current = User.objects.get(pk=user.pk)
        if not current.is_active or not constant_time_compare(expected, current.get_session_auth_hash()):
            clear_login(request)
            raise ImmediateHttpResponse(redirect("account_login"))
        # Keep the original user's hash so a concurrent revocation still invalidates the session.
        super().login(request, user)

    def set_password(self, user, password):
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])

    def get_reauthentication_methods(self, user):
        methods = super().get_reauthentication_methods(user)
        if user.is_authenticated and Authenticator.objects.filter(
            user=user, type=Authenticator.Type.TOTP
        ).exists():
            return [method for method in methods if method["id"] == "mfa_reauthenticate"]
        return methods

    def send_mail(self, template_prefix, email, context):
        try:
            super().send_mail(template_prefix, email, context)
        except OSError:
            logger.error("Account email delivery failed")

    def get_reset_password_from_key_url(self, key):
        uid, token = key.split("-", 1)
        path = reverse("account_reset_password_from_key", kwargs={"uidb36": uid, "key": token})
        return f"{settings.PUBLIC_ORIGIN}{path}"


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        sociallogin.token = None
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            from .mfa import reauthenticated_with_current_factor

            data = sociallogin.state.get("data") or {}
            if (
                not request.user.is_authenticated
                or not reauthenticated_with_current_factor(request)
                or data.get(GOOGLE_LINK_OWNER) != str(request.user.pk)
                or not constant_time_compare(
                    data.get("session_hash", ""), request.user.get_session_auth_hash()
                )
            ):
                raise PermissionDenied


class MFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text):
        return mfa_cipher().encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text):
        return mfa_cipher().decrypt(encrypted_text.encode()).decode()
