import os
from pathlib import Path

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "rest_framework",
    "users",
    "documents",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "documents.middleware.SameOriginApiMiddleware",
    "users.setup.SetupRequiredMiddleware",  # P24: first-run setup
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
ROOT_URLCONF = "hub.urls"
WSGI_APPLICATION = "hub.wsgi.application"
AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

INSTALLED_APPS += [
    "django.contrib.messages",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.mfa",
]
MIDDLEWARE += [
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "hub.context_processors.site",
        ],
    },
}]
LANGUAGE_CODE = "zh-hant"
# Project wording overrides for third-party catalogues (allauth), see locale/zh_Hant/LC_MESSAGES/django.po.
LOCALE_PATHS = [Path(__file__).resolve().parent.parent / "locale"]
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{validator}"}
    for validator in (
        "UserAttributeSimilarityValidator", "MinimumLengthValidator",
        "CommonPasswordValidator", "NumericPasswordValidator",
    )
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/app/"
LOGOUT_REDIRECT_URL = "/"
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "X-Hub-Client-IP"
ACCOUNT_ADAPTER = "users.adapters.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False
ACCOUNT_REAUTHENTICATION_METHODS = ["password", "mfa"]
ACCOUNT_PASSWORD_RESET_TOKEN_GENERATOR = "users.security.ResetTokenGenerator"
PASSWORD_RESET_TIMEOUT = 3600
SOCIALACCOUNT_ADAPTER = "users.adapters.SocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_REAUTHENTICATION_REQUIRED = True
GOOGLE_CONFIGURED = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [{
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "secret": os.environ["GOOGLE_CLIENT_SECRET"],
        }] if GOOGLE_CONFIGURED else [],
    }
}
MFA_ADAPTER = "users.adapters.MFAAdapter"
MFA_SUPPORTED_TYPES = ["totp"]
MFA_TOTP_ISSUER = "Knowledge Hub"
MFA_FORMS = {
    "authenticate": "users.mfa.AuthenticateForm",
}
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
    "LOCATION": "hub_security_cache",
    "KEY_FUNCTION": "users.security.cache_key",
}}
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "http://localhost:18080").rstrip("/")
if PUBLIC_ORIGIN.startswith("https://"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [PUBLIC_ORIGIN]
SECURE_REFERRER_POLICY = "same-origin"
CSRF_FAILURE_VIEW = "users.views.csrf_failure"
EMAIL_HOST = os.getenv("SMTP_HOST", "")
EMAIL_PORT = int(os.getenv("SMTP_PORT") or 587)
EMAIL_HOST_USER = os.getenv("SMTP_USERNAME", "")
EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL") or "knowledge-hub@localhost"
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST else "django.core.mail.backends.filebased.EmailBackend"
)
EMAIL_FILE_PATH = "/tmp/hub-mail"
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY")

DOCUMENT_STORAGE = os.getenv("DOCUMENT_STORAGE", "/var/lib/knowledge-hub/documents")
DOCUMENT_MAX_BATCH = int(os.getenv("DOCUMENT_MAX_BATCH") or 20)
# P23: every upload (not only videos) keeps this much of the disk free. Per-file limits are admin settings (P23c).
UPLOAD_MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
# Videos embedded in Markdown (P10). nginx serves them from DOCUMENT_STORAGE/videos/ after Django checks access;
VIDEO_ACCEL_PREFIX = "/_protected/videos/"

LOCAL_HTML_PREVIEW = os.getenv("LOCAL_HTML_PREVIEW", "false").lower() == "true"
