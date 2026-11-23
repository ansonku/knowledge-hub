from functools import wraps

from allauth.account.decorators import reauthentication_required
from allauth.account.utils import url_str_to_user_pk
from allauth.account.views._password_reset import PasswordResetFromKeyView
from allauth.mfa.models import Authenticator
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.base import AuthProcess
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import lifecycle
from .adapters import GOOGLE_LINK_OWNER
from .forms import AdminActionForm, InvitationForm, ProfileForm
from .mfa import reauthenticated_with_current_factor
from .models import AuditLog, User
from .permissions import CanReadLibrary, IsAdmin, has_role

ACTIVATION_SESSION = "hub_activation"


def account_payload(user):
    return {
        "id": str(user.pk), "username": user.username, "email": user.email,
        "display_name": user.display_name, "role": user.role,
    }


@never_cache
@ensure_csrf_cookie
@api_view(["GET", "PATCH"])
@permission_classes([CanReadLibrary])
def me(request):
    if request.method == "PATCH":
        form = ProfileForm(request.data, instance=request.user)
        if not form.is_valid():
            return Response({"errors": form.errors.get_json_data()}, status=400)
        save_profile(request.user)
    return Response({
        **account_payload(request.user), "csrf_token": get_token(request),
        "limits": {"bytes": settings.DOCUMENT_MAX_BYTES, "batch": settings.DOCUMENT_MAX_BATCH},
    })


@transaction.atomic
def save_profile(user):
    user.save(update_fields=["display_name", "updated_at"])
    lifecycle.audit("display_name_changed", user, user)


@never_cache
@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([IsAdmin])
def users_api(request):
    page = Paginator(User.objects.order_by("username"), 25).get_page(request.GET.get("page"))
    return Response({
        "count": page.paginator.count,
        "page": page.number,
        "page_count": page.paginator.num_pages,
        "results": [managed_account(user) for user in page.object_list],
        **management_context(request),
    })


def managed_account(user):
    return {**account_payload(user), "is_active": user.is_active, "pending_activation": user.pending_activation}


def management_context(request):
    return {
        "csrf_token": get_token(request),
        "roles": User.Role.choices,
        "notices": [
            {"text": str(message), "warning": message.level >= messages.WARNING}
            for message in messages.get_messages(request)
        ],
    }


@never_cache
@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([IsAdmin])
def user_api(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    form = AdminActionForm()
    audits = AuditLog.objects.filter(target=user).select_related("actor").order_by("-created_at")[:25]
    return Response({
        "account": managed_account(user),
        "actions": list(form.fields["action"].choices),
        "audit": [
            {
                "id": event.pk, "action": event.action, "created_at": event.created_at,
                "actor": event.actor.username if event.actor else None,
                "reason": event.metadata.get("reason"),
            }
            for event in audits
        ],
        **management_context(request),
    })


@require_safe
@never_cache
def account_index(request):
    return redirect("profile" if request.user.is_authenticated else "account_login")


@login_required
@require_http_methods(["GET", "POST", "HEAD"])
@never_cache
def profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        save_profile(request.user)
        messages.success(request, "已更新顯示名稱。")
        return redirect("profile")
    return render(request, "users/profile.html", {"form": form})


@login_required
@require_POST
@reauthentication_required(app="allauth.socialaccount")
@never_cache
def google_connect(request):
    if not settings.GOOGLE_CONFIGURED:
        raise Http404
    if not reauthenticated_with_current_factor(request):
        raise PermissionDenied
    provider = get_adapter().get_provider(request, "google")
    return provider.redirect(request, AuthProcess.CONNECT, data={
        GOOGLE_LINK_OWNER: str(request.user.pk),
        "session_hash": request.user.get_session_auth_hash(),
    })


@require_safe
@never_cache
def activation_link(request, user_id, token):
    user = get_object_or_404(User, pk=user_id)
    if not lifecycle.activation_is_valid(user, token):
        return render(request, "users/activate.html", status=400)
    request.session[ACTIVATION_SESSION] = {"id": str(user_id), "token": token}
    return redirect("activation_form", user_id=user_id)


@require_http_methods(["GET", "POST", "HEAD"])
@never_cache
@transaction.atomic
def activation_form(request, user_id):
    token = request.session.get(ACTIVATION_SESSION) or {}
    users = User.objects.select_for_update() if request.method == "POST" else User.objects.all()
    user = get_object_or_404(users, pk=user_id)
    if token.get("id") != str(user_id) or not lifecycle.activation_is_valid(user, token.get("token", "")):
        return render(request, "users/activate.html", status=400)
    form = SetPasswordForm(user, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        lifecycle.activate(user, form.cleaned_data["new_password1"])
        request.session.pop(ACTIVATION_SESSION, None)
        messages.success(request, "帳號已啟用，請登入。")
        return redirect("account_login")
    return render(request, "users/activate.html", {"form": form})


class LockedPasswordResetView(PasswordResetFromKeyView):
    @transaction.atomic
    def dispatch(self, request, uidb36, key, **kwargs):
        if request.method == "POST":
            try:
                user_id = url_str_to_user_pk(uidb36)
            except (TypeError, ValueError, ValidationError):
                raise Http404 from None
            User.objects.select_for_update().filter(pk=user_id).first()
        return super().dispatch(request, uidb36, key, **kwargs)


def admin_required(view):
    @login_required
    @wraps(view)
    def checked(request, *args, **kwargs):
        if not has_role(request.user, User.Role.ADMIN):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return checked


def lock_admin_actor(request):
    # Lock in the same order for role changes, deactivations and other admin actions.
    admins = list(User.objects.select_for_update().filter(role=User.Role.ADMIN).order_by("pk"))
    actor = next((admin for admin in admins if admin.pk == request.user.pk), None)
    if not actor or not actor.is_active or actor.get_session_auth_hash() != request.user.get_session_auth_hash():
        raise PermissionDenied
    return actor, sum(admin.is_active for admin in admins)


@admin_required
@require_http_methods(["GET", "POST"])
@reauthentication_required(app="users", allow_get=True)
@never_cache
def manage_users(request):
    form = InvitationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                actor, _ = lock_admin_actor(request)
                user = form.save(commit=False)
                user.is_active = False
                user.pending_activation = True
                user.set_unusable_password()
                user.save()
                lifecycle.send_activation(request, user)
                lifecycle.audit("invited", user, actor, role=user.role)
        except IntegrityError:
            form.add_error(None, "帳號名稱或電子郵件已被使用。")
        else:
            messages.success(request, "已建立待啟用帳號。")
            return redirect("manage_users")
    page = Paginator(User.objects.order_by("username"), 25).get_page(request.GET.get("page"))
    return render(request, "users/manage.html", {"form": form, "page": page})


def apply_admin_action(request, actor, user, active_admin_count, data):
    action = data["action"]
    actions = AdminActionForm.Action
    if user == actor and action in (actions.DISABLE, actions.ROLE, actions.MFA):
        raise ValidationError("這項操作需要由另一位管理員執行。")
    last_admin = user.is_active and user.role == User.Role.ADMIN and active_admin_count == 1
    if last_admin and (action == actions.DISABLE or (action == actions.ROLE and data["role"] != User.Role.ADMIN)):
        raise ValidationError("必須保留至少一位使用中的管理員。")

    if action == actions.ROLE:
        old_role = user.role
        user.role = data["role"]
        user.save(update_fields=["role", "updated_at"])
        lifecycle.audit("role_changed", user, actor, old_role=old_role, role=user.role)
        lifecycle.notify(request, user, "Knowledge Hub 角色變更", f"你的角色已變更為 {user.get_role_display()}。")
    elif action in (actions.DISABLE, actions.ENABLE):
        if user.pending_activation:
            raise ValidationError("請先完成帳號啟用。")
        user.is_active = action == actions.ENABLE
        user.save(update_fields=["is_active", "updated_at"])
        lifecycle.revoke_sessions(user)
        lifecycle.audit("enabled" if user.is_active else "disabled", user, actor)
        lifecycle.notify(request, user, "Knowledge Hub 帳號狀態", "你的帳號已重新啟用。" if user.is_active else "你的帳號已停用。")
    elif action == actions.RESEND:
        lifecycle.send_activation(request, user)
        lifecycle.audit("activation_resent", user, actor)
    elif action == actions.PASSWORD:
        lifecycle.send_password_reset(request, user)
        lifecycle.audit("password_reset_requested", user, actor)
    elif action == actions.MFA:
        authenticators = Authenticator.objects.filter(user=user)
        if not authenticators.exists():
            raise ValidationError("此帳號尚未啟用雙因素驗證。")
        authenticators.delete()
        lifecycle.revoke_sessions(user)
        lifecycle.audit("mfa_admin_reset", user, actor, reason=data["reason"], identity_verified=True)
        lifecycle.notify(request, user, "Knowledge Hub 雙因素驗證重設", "管理員已重設雙因素驗證。請重新登入並設定驗證器。")


@admin_required
@require_http_methods(["GET", "POST"])
@reauthentication_required(app="users", allow_get=True)
@never_cache
def manage_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    form = AdminActionForm(request.POST if request.method == "POST" else None, initial={"role": user.role})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                actor, count = lock_admin_actor(request)
                user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
                apply_admin_action(request, actor, user, count, form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "已完成帳號操作。")
            return redirect(reverse("manage_user", kwargs={"user_id": user_id}))
    audits = AuditLog.objects.filter(target=user).select_related("actor").order_by("-created_at")[:25]
    return render(request, "users/manage_detail.html", {"target": user, "form": form, "audits": audits})


@never_cache
def csrf_failure(request, reason=""):
    return render(request, "users/csrf_failure.html", status=403)
