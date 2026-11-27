import secrets

from allauth.account.decorators import reauthentication_required
from allauth.account.internal.flows.login import clear_authentication_records, get_authentication_records
from allauth.account.internal.flows.reauthentication import did_recently_reauthenticate
from allauth.account.internal.stagekit import clear_login, get_pending_stage
from allauth.mfa.adapter import get_adapter
from allauth.mfa.base import forms
from allauth.mfa.base.internal.flows import check_rate_limit
from allauth.mfa.base import views as base_views
from allauth.mfa.base.views import authenticate as allauth_authenticate
from allauth.mfa.internal.flows import trust as trust_flows
from allauth.mfa.models import Authenticator
from allauth.mfa.stages import AuthenticateStage
from allauth.mfa.totp import views
from allauth.mfa.totp.internal import flows
from allauth.mfa.totp.internal.auth import SECRET_SESSION_KEY
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from .adapters import LOGIN_HASH
from .lifecycle import audit, revoke_sessions
from .models import User
from .security import recovery_verifier


RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
RECOVERY_COUNT = 10


def normalized(code):
    return "".join(char for char in code.upper() if char.isalnum())


def issue_recovery_codes(authenticator):
    """P25: ten one-time codes like 7Q4M-2KXD; only their HMAC is kept. Replaces any earlier set."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    authenticator.data["recovery_verifiers"] = [recovery_verifier(normalized(code)) for code in codes]
    authenticator.save(update_fields=["data"])
    return codes


def recovery_codes_left(user):
    auth = Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).only("data").first()
    return None if auth is None else len(auth.data.get("recovery_verifiers", []))


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
                    # P25: XXXX-XXXX codes in any case and with or without the dash; older 20-hex codes as given.
                    candidates = {recovery_verifier(normalized(code)), recovery_verifier(code.strip())}
                    verifiers = auth.data.get("recovery_verifiers", [])
                    remaining = [value for value in verifiers if not any(constant_time_compare(value, c) for c in candidates)]
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
        target = local_path(request.GET.get("next", ""))
        if target:
            request.session[AFTER_SETUP] = target  # P25: e.g. the admin page that asked for two-factor
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
        codes = issue_recovery_codes(authenticator)
        revoke_sessions(user)
        clear_authentication_records(self.request)
        update_session_auth_hash(self.request, user)
        return render(self.request, "users/recovery_codes.html", {"codes": codes, "done_url": after_setup(self.request)})


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
    if request.method == "POST":
        # P25: "10 天內不再詢問" is a checkbox here; the trust step below acts on it without a page of its own.
        if request.POST.get("trust") == "on":
            request.session[TRUST_REQUESTED] = True
        else:
            request.session.pop(TRUST_REQUESTED, None)
    return allauth_authenticate(request)


TRUST_REQUESTED = "mfa_trust_requested"


class TrustView(base_views.TrustView):
    """P25: allauth asks "trust this browser?" on a page after the code; the code page already asked."""

    def get(self, request, *args, **kwargs):
        return self.finish(request)

    def post(self, request, *args, **kwargs):
        return self.finish(request)

    def finish(self, request):
        stage = request._login_stage
        response = stage.exit()
        if request.session.pop(TRUST_REQUESTED, False):
            trust_flows.trust_browser(request, stage.login.user, response)
        return response


trust = TrustView.as_view()


def fingerprint_with_sessions(original):
    """Signing out everywhere (session_version) also ends trusted browsers; allauth already covers the password
    and the authenticators."""
    def fingerprint(user):
        return salted_hmac("users.mfa.trust", f"{original(user)}|{getattr(user, 'session_version', 0)}", algorithm="sha256").hexdigest()
    fingerprint.wrapped = original
    return fingerprint


@method_decorator(never_cache, name="dispatch")
@method_decorator(reauthentication_required(app="users", allow_get=False), name="post")
class RegenerateRecoveryCodesView(View):
    """P25: a new set of recovery codes (after confirming who you are); the old set stops working."""

    def get(self, request):
        if recovery_codes_left(request.user) is None:
            return redirect("mfa_index")
        return render(request, "users/recovery_regenerate.html", {"left": recovery_codes_left(request.user)})

    @transaction.atomic
    def post(self, request):
        auth = Authenticator.objects.select_for_update().filter(user=request.user, type=Authenticator.Type.TOTP).first()
        if auth is None:
            return redirect("mfa_index")
        codes = issue_recovery_codes(auth)
        audit("mfa_recovery_regenerated", request.user, actor=request.user)
        return render(request, "users/recovery_codes.html", {"codes": codes, "regenerated": True, "done_url": reverse("mfa_index")})


AFTER_SETUP = "mfa_after_setup"


def local_path(value):
    """Only same-site paths (no scheme, host or //) are kept as a place to return to."""
    return value if value and value.startswith("/") and not value.startswith("//") and "\\" not in value else ""


class IndexView(base_views.IndexView):
    """P25: the management page also shows how many recovery codes are left (never the codes)."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        left = recovery_codes_left(self.request.user)
        context.update({"recovery_left": left, "recovery_total": RECOVERY_COUNT,
                        "recovery_used": RECOVERY_COUNT - left if left is not None else 0,
                        "admin_required": mfa_status_required(self.request.user)})
        return context


index = never_cache(IndexView.as_view())


def mfa_status_required(user):
    from .permissions import mfa_required_for
    return mfa_required_for(user)


def after_setup(request):
    """Where 完成 on the recovery-code page goes: the page that sent the person here, or the management page."""
    return request.session.pop(AFTER_SETUP, "") or reverse("mfa_index")
