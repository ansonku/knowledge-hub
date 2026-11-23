from rest_framework.permissions import BasePermission

from .models import User


def has_role(user, *roles):
    return user.is_authenticated and user.is_active and user.role in roles


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, User.Role.ADMIN)


class CanReadLibrary(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, *User.Role.values)
