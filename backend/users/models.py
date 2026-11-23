import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


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
