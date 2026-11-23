from allauth.account import signals as account_signals
from allauth.mfa import signals as mfa_signals
from allauth.socialaccount import signals as social_signals
from django.contrib.auth.signals import user_logged_in, user_logged_out

from .lifecycle import audit


def register_signals():
    handlers = [
        (user_logged_in, "login"),
        (user_logged_out, "logout"),
        (account_signals.password_changed, "password_changed"),
        (account_signals.password_reset, "password_reset"),
        (mfa_signals.authenticator_added, "mfa_enabled"),
        (mfa_signals.authenticator_removed, "mfa_disabled"),
    ]
    for signal, action in handlers:
        signal.connect(account_event(action), weak=False, dispatch_uid=f"hub.audit.{action}")
    social_signals.social_account_added.connect(google_linked, dispatch_uid="hub.audit.google_linked")
    social_signals.social_account_removed.connect(google_unlinked, dispatch_uid="hub.audit.google_unlinked")


def account_event(action):
    def record(sender, user, **kwargs):
        if user and user.is_authenticated:
            audit(action, user, user)

    return record


def google_linked(sender, request, **kwargs):
    audit("google_linked", request.user, request.user)


def google_unlinked(sender, request, **kwargs):
    audit("google_unlinked", request.user, request.user)
