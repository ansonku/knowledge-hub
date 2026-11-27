from allauth.socialaccount.providers.google import views as google_views
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from django.conf import settings
from django.http import Http404
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache

from . import mfa, views


def unavailable(request, *args, **kwargs):
    raise Http404


@never_cache
def google_login(request):
    if not settings.GOOGLE_CONFIGURED:
        raise Http404
    return google_views.oauth2_login(request)


class GoogleOIDCAdapter(google_views.GoogleOAuth2Adapter):
    def complete_login(self, request, app, token, **kwargs):
        if not kwargs["response"].get("id_token"):
            raise OAuth2Error("Google did not return an ID token.")
        return super().complete_login(request, app, token, **kwargs)

    def _decode_id_token(self, app, id_token):
        claims = super()._decode_id_token(app, id_token)
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise OAuth2Error("Google ID token has no subject.")
        return claims


oidc_callback = google_views.OAuth2CallbackView.adapter_view(GoogleOIDCAdapter)


@never_cache
def google_callback(request):
    if not settings.GOOGLE_CONFIGURED:
        raise Http404
    return oidc_callback(request)


def private_link(view):
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        if kwargs.get("key") != views.LockedPasswordResetView.reset_url_key:
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return wrapped


urlpatterns = [
    path("accounts/", views.account_index),
    path("api/auth/me", views.me, name="auth_me"),
    path("api/users/", views.users_api, name="users_api"),
    path("api/users/<uuid:user_id>/", views.user_api, name="user_api"),
    path("accounts/manage/", views.manage_users, name="manage_users"),
    path("accounts/manage/<uuid:user_id>/", views.manage_user, name="manage_user"),
    path("accounts/activate/<uuid:user_id>/", views.activation_form, name="activation_form"),
    path("accounts/activate/<uuid:user_id>/<str:token>/", private_link(views.activation_link), name="activate"),
    re_path(
        r"^accounts/password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>[^/]+)/$",
        private_link(never_cache(views.LockedPasswordResetView.as_view())),
        name="account_reset_password_from_key",
    ),
    path("accounts/google/connect/", views.google_connect, name="google_connect"),
    path("accounts/google/login/token/", unavailable),
    path("accounts/google/login/", google_login),
    path("accounts/google/login/callback/", private_link(google_callback)),
    path("accounts/email/", unavailable),
    path("accounts/password/set/", unavailable),
    path("accounts/2fa/authenticate/", mfa.authenticate, name="mfa_authenticate"),
    path("accounts/2fa/totp/activate/", mfa.ActivateTOTPView.as_view(), name="mfa_activate_totp"),
    path("accounts/2fa/totp/deactivate/", mfa.DeactivateTOTPView.as_view(), name="mfa_deactivate_totp"),
    path("accounts/2fa/trust/", mfa.trust, name="mfa_trust"),
    path("accounts/2fa/", mfa.index, name="mfa_index"),
    path("accounts/2fa/recovery-codes/regenerate/", mfa.RegenerateRecoveryCodesView.as_view(), name="mfa_regenerate_recovery"),
    path("api/admin/security/", views.security_settings, name="security_settings"),
    path("accounts/", include("allauth.urls")),
]
