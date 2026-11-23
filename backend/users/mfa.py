import secrets

from allauth.account.internal.flows.login import clear_authentication_records, get_authentication_records
from allauth.account.internal.flows.reauthentication import did_recently_reauthenticate
from allauth.account.internal.stagekit import clear_login, get_pending_stage
from allauth.mfa.adapter import get_adapter
from allauth.mfa.base import forms
from allauth.mfa.base.internal.flows import check_rate_limit
from allauth.mfa.base.views import authenticate as allauth_authenticate
from allauth.mfa.models import Authenticator
from allauth.mfa.stages import AuthenticateStage
from allauth.mfa.totp import views
from allauth.mfa.totp.internal import flows
from allauth.mfa.totp.internal.auth import SECRET_SESSION_KEY
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from .adapters import LOGIN_HASH
from .lifecycle import revoke_sessions
from .models import User
from .security import recovery_verifier


class AuthenticateForm(forms.AuthenticateForm):
    def clean_code(self):
        clear_rate_limit = check_rate_limit(self.user)
        code = self.cleaned_data["code"]
        with transaction.atomic():
            auth = Authenticator.objects.select_for_update().filter(
                user=self.user, type=Authenticator.Type.TOTP,
            ).first()
            if auth:
                valid = auth.wrap().validate_code(code)
                if not valid:
                    candidate = recovery_verifier(code)
                    verifiers = auth.data.get("recovery_verifiers", [])
                    remaining = [value for value in verifiers if not constant_time_compare(value, candidate)]
                    valid = len(remaining) != len(verifiers)
                    if valid:
                        auth.data["recovery_verifiers"] = remaining
                        auth.save(update_fields=["data"])
                if valid:
                    auth.user = self.user
                    self.authenticator = auth
                    clear_rate_limit()
                    return code
        if auth:
            self._emit_authentication_failed(auth)
        raise get_adapter().validation_error("incorrect_code")


@method_decorator(never_cache, name="dispatch")
class ActivateTOTPView(views.ActivateTOTPView):
    def dispatch(self, request, *args, **kwargs):
        adapter = get_adapter()
        secret = request.session.pop(SECRET_SESSION_KEY, None)
        if secret:
            request.session[SECRET_SESSION_KEY] = adapter.decrypt(secret)
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            secret = request.session.get(SECRET_SESSION_KEY)
            if secret:
                request.session[SECRET_SESSION_KEY] = adapter.encrypt(secret)

    @transaction.atomic
    def form_valid(self, form):
        user = User.objects.select_for_update().get(pk=self.request.user.pk)
        if not user.is_active or user.get_session_auth_hash() != self.request.user.get_session_auth_hash():
            return redirect("account_login")
        if Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
            return redirect("mfa_index")
        authenticator, _ = flows.activate_totp(self.request, form)
        codes = [secrets.token_hex(10) for _ in range(10)]
        authenticator.data["recovery_verifiers"] = [recovery_verifier(code) for code in codes]
        authenticator.save(update_fields=["data"])
        revoke_sessions(user)
        clear_authentication_records(self.request)
        update_session_auth_hash(self.request, user)
        return render(self.request, "users/recovery_codes.html", {"codes": codes})


@method_decorator(never_cache, name="dispatch")
class DeactivateTOTPView(views.DeactivateTOTPView):
    @transaction.atomic
    def form_valid(self, form):
        user = User.objects.select_for_update().get(pk=self.request.user.pk)
        if not user.is_active or user.get_session_auth_hash() != self.request.user.get_session_auth_hash():
            return redirect("account_login")
        response = super().form_valid(form)
        revoke_sessions(user)
        clear_authentication_records(self.request)
        update_session_auth_hash(self.request, user)
        return response


def reauthenticated_with_current_factor(request):
    if not did_recently_reauthenticate(request):
        return False
    records = get_authentication_records(request, request.user)
    factor = "mfa" if Authenticator.objects.filter(
        user=request.user, type=Authenticator.Type.TOTP
    ).exists() else "password"
    latest = records[-1]
    return latest.get("reauthenticated", False) and latest["method"] == factor


@never_cache
def authenticate(request):
    stage = get_pending_stage(request)
    if stage and stage.key == AuthenticateStage.key:
        user = stage.login.user
        if (
            not user
            or not user.is_active
            or not constant_time_compare(request.session.get(LOGIN_HASH, ""), user.get_session_auth_hash())
            or not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()
        ):
            clear_login(request)
            request.session.pop(LOGIN_HASH, None)
            return redirect("account_login")
    return allauth_authenticate(request)
