import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import salted_hmac


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=6, choices=Role.choices, default=Role.VIEWER)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["email"]

    pending_activation = models.BooleanField(default=False)
    activation_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    session_version = models.PositiveBigIntegerField(default=0)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(models.functions.Lower("email"), name="unique_user_email_ci")
        ]

    def _get_session_auth_hash(self, secret=None):
        if self.session_version == 0:
            return super()._get_session_auth_hash(secret)
        return salted_hmac(
            "users.User.session",
            f"{self.password}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()


class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    target = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=48)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class SetupState(models.Model):
    """P24: the first-run setup (one row, pk=1), opened by `prepare_setup` while no admin exists.

    The setup code itself lives only in a host-readable file; this keeps its hash."""
    opened_at = models.DateTimeField(null=True, blank=True)
    code_hash = models.CharField(max_length=256, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
