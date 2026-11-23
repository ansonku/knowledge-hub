import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import salted_hmac


def cache_key(key, prefix, version):
    return hashlib.sha256(f"{prefix}:{version}:{key}".encode()).hexdigest()


def mfa_cipher():
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        digest = salted_hmac("users.mfa.encryption", "", algorithm="sha256").digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def recovery_verifier(code):
    return salted_hmac("users.mfa.recovery", code, algorithm="sha256").hexdigest()


class ResetTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}:{user.session_version}:{user.is_active}"

    def check_token(self, user, token):
        return bool(user and user.is_active and super().check_token(user, token))


reset_tokens = ResetTokenGenerator()
