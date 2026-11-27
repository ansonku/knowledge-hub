from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "users"

    def ready(self):
        from .signals import register_signals

        register_signals()
        # P25: trusted browsers also end when someone signs out everywhere (see users.mfa).
        from allauth.mfa.internal.flows import trust

        from .mfa import fingerprint_with_sessions
        if not hasattr(trust.create_config_fingerprint, "wrapped"):
            trust.create_config_fingerprint = fingerprint_with_sessions(trust.create_config_fingerprint)
