import logging
import uuid
from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.account.utils import user_pk_to_url_str
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse

from .models import AuditLog
from .security import reset_tokens

logger = logging.getLogger(__name__)
ACTIVATION_SALT = "users.email-activation"


def audit(action, target, actor=None, **metadata):
    AuditLog.objects.create(actor=actor, target=target, action=action, metadata=metadata)


def notify(request, user, subject, body):
    from django.contrib import messages

    def deliver():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        except Exception:
            logger.error("Account notification delivery failed")
            messages.warning(request, "郵件寄送失敗，請確認郵件設定後重試。", extra_tags="members")

    transaction.on_commit(deliver)


def send_activation(request, user):
    if not user.pending_activation or user.is_active:
        raise ValidationError("此帳號目前沒有待處理的邀請。")
    user.activation_nonce = uuid.uuid4()
    user.save(update_fields=["activation_nonce", "updated_at"])
    token = signing.dumps(str(user.activation_nonce), salt=ACTIVATION_SALT)
    path = reverse("activate", kwargs={"user_id": user.pk, "token": token})
    notify(request, user, "Knowledge Hub 帳號啟用", f"請在 24 小時內設定密碼：\n{settings.PUBLIC_ORIGIN}{path}")


def activation_is_valid(user, token):
    if user.is_active or not user.pending_activation:
        return False
    try:
        nonce = signing.loads(token, salt=ACTIVATION_SALT, max_age=timedelta(hours=24))
    except signing.BadSignature:
        return False
    return nonce == str(user.activation_nonce)


def activate(user, password):
    user.set_password(password)
    user.is_active = True
    user.pending_activation = False
    user.activation_nonce = uuid.uuid4()
    user.save(update_fields=[
        "password", "is_active", "pending_activation", "activation_nonce", "updated_at",
    ])
    EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})
    audit("activated", user, user)


def send_password_reset(request, user):
    if not user.is_active:
        raise ValidationError("只有使用中的帳號可以重設密碼。")
    path = reverse("account_reset_password_from_key", kwargs={
        "uidb36": user_pk_to_url_str(user), "key": reset_tokens.make_token(user),
    })
    notify(request, user, "Knowledge Hub 密碼重設", f"請在一小時內重設密碼：\n{settings.PUBLIC_ORIGIN}{path}")


def revoke_sessions(user):
    user.session_version += 1
    user.save(update_fields=["session_version", "updated_at"])
