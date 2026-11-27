"""P24: first-run setup. While no active admin exists, `prepare_setup` (run at container start) opens setup for an
hour and writes a one-time setup code to a host-readable file. Within the hour the wizard needs no code; after it,
the code is required. Finishing creates the first admin, signs them in and closes setup for good.

The code is a secret: only its hash is stored and logs name the file, never the code."""
import logging
import os
import secrets
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from hub import about

from .lifecycle import audit
from .models import SetupState, User

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=1)
PERMIT = timedelta(minutes=30)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
CODE_LENGTH = 12
MAX_ATTEMPTS, ATTEMPT_PERIOD = 5, 10 * 60
BOOTSTRAP_LOCK = "knowledge-hub:bootstrap"  # shared with create_hub_admin
SESSION_KEY = "setup_permit_until"


def code_file():
    return Path(settings.DOCUMENT_STORAGE) / "setup-code.txt"


def has_admin():
    return User.objects.filter(role=User.Role.ADMIN, is_active=True).exists()


# ---- Is setup required? --------------------------------------------------------------------------
# Only a pending row means setup. "Finished" and "never opened" (tests, old installs before prepare_setup ran)
# cannot change back while this process runs, so they are remembered; the pending state is checked each time.
_settled = False


def reset_cache():
    global _settled
    _settled = False


def pending():
    global _settled
    if _settled:
        return False
    try:
        state = SetupState.objects.filter(pk=1).only("completed_at").first()
    except DatabaseError:
        return False
    if state is None or state.completed_at is not None:
        _settled = True
        return False
    return True


def window_left(state, now=None):
    if state.opened_at is None:
        return timedelta(0)
    return max(timedelta(0), state.opened_at + WINDOW - (now or timezone.now()))


# ---- Opening and closing -------------------------------------------------------------------------
def new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def formatted(code):
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def write_code_file(code):
    target = code_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".setup-code-")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(formatted(code) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def remove_code_file():
    try:
        code_file().unlink()
    except FileNotFoundError:
        pass


def open_setup(now=None):
    """Open (or reopen) setup for an hour with a new code; returns the code file. Called at start without an admin."""
    code = new_code()
    write_code_file(code)
    SetupState.objects.update_or_create(pk=1, defaults={
        "opened_at": now or timezone.now(), "code_hash": make_password(code), "completed_at": None,
    })
    reset_cache()
    return code_file()


def close_setup(now=None):
    """Mark setup finished and forget the code (also called by create_hub_admin and at start when an admin exists)."""
    SetupState.objects.update_or_create(pk=1, defaults={"code_hash": "", "completed_at": now or timezone.now()})
    remove_code_file()
    global _settled
    _settled = True


# ---- Middleware ----------------------------------------------------------------------------------
OPEN_PATHS = ("/api/health", "/api/setup/", "/setup/", "/assets/", "/favicon")


class SetupRequiredMiddleware:
    """While setup is pending, pages go to /setup/ and the API answers 503 with setup_required.

    Workspace pages are served by nginx without Django; the frontend follows the 503 there."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith(OPEN_PATHS) or not pending():
            return self.get_response(request)
        if path.startswith("/api/"):
            return JsonResponse({"detail": "系統尚未完成首次設定。", "setup_required": True}, status=503)
        return HttpResponseRedirect("/setup/")


# ---- API -----------------------------------------------------------------------------------------
def client_key(request):
    address = request.META.get("HTTP_X_HUB_CLIENT_IP") or request.META.get("REMOTE_ADDR", "")
    return f"setup-attempts:{address}"


def permitted(request):
    until = request.session.get(SESSION_KEY)
    return bool(until) and timezone.now().timestamp() < until


def grant(request):
    request.session[SESSION_KEY] = (timezone.now() + PERMIT).timestamp()


def checks():
    """What the deployment looks like; read only. Secrets are .env settings and never pass through the web."""
    try:
        usage = shutil.disk_usage(settings.DOCUMENT_STORAGE)
        disk = {"total_bytes": usage.total, "free_bytes": usage.free}
    except OSError:
        disk = None
    storage = Path(settings.DOCUMENT_STORAGE)
    return {
        "https": settings.PUBLIC_ORIGIN.startswith("https://"), "origin": settings.PUBLIC_ORIGIN,
        "database": True,  # this request reached the database
        "storage_writable": storage.is_dir() and os.access(storage, os.W_OK),
        "disk": disk,
        "smtp": bool(settings.EMAIL_HOST), "google_login": settings.GOOGLE_CONFIGURED,
        "mfa_key": bool(settings.MFA_ENCRYPTION_KEY),
    }


@never_cache
@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def setup_status(request):
    if not pending():
        return Response({"required": False})
    state = SetupState.objects.get(pk=1)
    left = window_left(state)
    return Response({
        "required": True,
        "window_seconds": int(left.total_seconds()),
        "code_required": not left and not permitted(request),
        "permitted": permitted(request),
        "code_file": str(code_file()),
        "about": about.public(),
        "checks": checks(),
    })


class VerifyInput(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True, max_length=40)


@never_cache
@api_view(["POST"])
@permission_classes([AllowAny])
def setup_verify(request):
    """Start setting up: free within the hour, otherwise with the setup code. Grants a 30-minute permit."""
    if not pending():
        return Response({"detail": "首次設定已經完成。"}, status=status.HTTP_410_GONE)
    payload = VerifyInput(data=request.data)
    payload.is_valid(raise_exception=True)
    state = SetupState.objects.get(pk=1)
    if window_left(state):
        grant(request)
        return Response({"permitted": True})
    key = client_key(request)
    attempts = cache.get(key, 0)
    if attempts >= MAX_ATTEMPTS:
        raise Throttled(wait=ATTEMPT_PERIOD, detail="設定碼輸入錯誤太多次，請 10 分鐘後再試。")
    code = "".join(ch for ch in payload.validated_data.get("code", "").upper() if ch.isalnum())
    if not code or not state.code_hash or not check_password(code, state.code_hash):
        cache.set(key, attempts + 1, ATTEMPT_PERIOD)
        left = MAX_ATTEMPTS - attempts - 1
        logger.warning("Wrong setup code (%d attempts left for this client).", left)
        raise ValidationError({"code": f"設定碼不正確，還可以再試 {left} 次。" if left else "設定碼輸入錯誤太多次，請 10 分鐘後再試。"})
    cache.delete(key)
    grant(request)
    return Response({"permitted": True})


class AdminInput(serializers.Serializer):
    display_name = serializers.CharField(max_length=150)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=4096, trim_whitespace=False)


class SiteInput(serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False)
    tagline = serializers.CharField(max_length=160, required=False, allow_blank=True)
    storage_limit_gb = serializers.IntegerField(min_value=1, max_value=1_000_000, required=False, allow_null=True)


class CompleteInput(serializers.Serializer):
    terms_version = serializers.IntegerField()
    admin = AdminInput()
    site = SiteInput(required=False)


@never_cache
@api_view(["POST"])
@permission_classes([AllowAny])
def setup_complete(request):
    if not pending():
        return Response({"detail": "首次設定已經完成。"}, status=status.HTTP_410_GONE)
    if not permitted(request):
        return Response({"detail": "設定許可已過期，請重新開始設定。", "permit_expired": True}, status=status.HTTP_403_FORBIDDEN)
    payload = CompleteInput(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    if data["terms_version"] != about.TERMS_VERSION:
        raise ValidationError({"terms_version": "條款已更新，請重新閱讀後再同意。"})
    form = data["admin"]
    user = User(username=form["username"], email=form["email"].lower(), display_name=form["display_name"].strip(), role=User.Role.ADMIN)
    try:
        user.full_clean(exclude=["password"])
        validate_password(form["password"], user)
    except DjangoValidationError as error:
        raise ValidationError(error.message_dict if hasattr(error, "message_dict") else {"password": error.messages}) from None
    if User.objects.filter(email__iexact=user.email).exists():
        raise ValidationError({"email": "這個 Email 已經被使用。"})
    user.set_password(form["password"])
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [BOOTSTRAP_LOCK])
            if has_admin() or not SetupState.objects.select_for_update().filter(pk=1, completed_at__isnull=True).exists():
                return Response({"detail": "首次設定已經完成。"}, status=status.HTTP_410_GONE)
            user.save()
            EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
            apply_site(data.get("site") or {}, user)
            require_admin_mfa(user)
            audit("admin_bootstrapped", user, actor=user, via="setup", terms_version=about.TERMS_VERSION)
            close_setup()
    except IntegrityError:
        raise ValidationError({"username": "帳號或 Email 已經被使用。"}) from None
    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session.pop(SESSION_KEY, None)
    logger.info("First-run setup completed; administrator %s created.", user.pk)
    return Response({"done": True, "next": "/app/admin/"}, status=status.HTTP_201_CREATED)


def require_admin_mfa(user):
    """P25: a site made by the wizard asks its admins to use two-factor from the start."""
    from documents.models import SiteSettings
    SiteSettings.objects.update_or_create(pk=1, defaults={"require_admin_mfa": True, "updated_by": user})


def apply_site(site, user):
    if not site:
        return
    from documents.models import SiteSettings  # documents imports users; keep this one-way at import time
    settings_row, _ = SiteSettings.objects.select_for_update().get_or_create(pk=1)
    if site.get("name", "").strip():
        settings_row.name = site["name"].strip()
    if "tagline" in site:
        settings_row.tagline = site["tagline"].strip()
    if site.get("storage_limit_gb"):
        settings_row.storage_limit = site["storage_limit_gb"] * 1024 ** 3
    settings_row.updated_by = user
    settings_row.save()
