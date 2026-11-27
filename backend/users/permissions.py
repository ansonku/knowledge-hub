from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .models import User


def has_role(user, *roles):
    return user.is_authenticated and user.is_active and user.role in roles


MFA_REQUIRED = "管理員需要先開啟雙因素驗證，才能使用管理功能。"


def mfa_required_for(user):
    """P25: whether this admin is held back by the site's "require admins to use two-factor" setting."""
    if not has_role(user, User.Role.ADMIN):
        return False
    from allauth.mfa.models import Authenticator
    from documents.models import SiteSettings  # documents imports users; keep this one-way at import time
    if not SiteSettings.current().require_admin_mfa:
        return False
    return not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


def ensure_admin_mfa(user):
    """Raise 403 with mfa_required for an admin without two-factor while the site requires it."""
    if mfa_required_for(user):
        raise PermissionDenied({"detail": MFA_REQUIRED, "mfa_required": True})


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        if not has_role(request.user, User.Role.ADMIN):
            return False
        ensure_admin_mfa(request.user)  # P25
        return True


class CanReadLibrary(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, *User.Role.values)
