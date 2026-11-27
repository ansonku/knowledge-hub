"""P25: small helpers for the account templates."""
from django import template

register = template.Library()

# What a confirm-who-you-are page is for, from where it will return.
PURPOSES = (
    ("/accounts/2fa/totp/deactivate/", "停用雙因素驗證"),
    ("/accounts/2fa/recovery-codes/regenerate/", "重新產生復原碼"),
    ("/accounts/2fa/totp/activate/", "啟用雙因素驗證"),
    ("/accounts/google/", "綁定或解除 Google 帳號"),
    ("/accounts/password/change/", "變更密碼"),
    ("/app/admin/members/", "管理成員"),
    ("/accounts/manage/", "管理成員"),
)


@register.simple_tag(takes_context=True)
def reauth_purpose(context):
    request = context.get("request")
    target = (request.GET.get("next") or request.POST.get("next") or "") if request else ""
    for prefix, label in PURPOSES:
        if target.startswith(prefix):
            return label
    return "這項操作"


@register.filter
def group4(value):
    """EYMIK4BS… → EYMI K4BS … (easier to type into an authenticator app)."""
    value = str(value or "")
    return " ".join(value[i:i + 4] for i in range(0, len(value), 4))


@register.simple_tag
def recovery_left(user):
    from users.mfa import recovery_codes_left
    return recovery_codes_left(user)
