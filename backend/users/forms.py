from django import forms

from .models import User


class InvitationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "display_name", "role")
        labels = {"username": "帳號名稱", "email": "電子郵件", "display_name": "顯示名稱", "role": "角色"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("此電子郵件已被使用。")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name",)
        labels = {"display_name": "顯示名稱"}


class AdminActionForm(forms.Form):
    class Action:
        ROLE = "role"
        DISABLE = "disable"
        ENABLE = "enable"
        RESEND = "resend"
        PASSWORD = "password"
        MFA = "mfa"

    action = forms.ChoiceField(choices=[
        (Action.ROLE, "變更角色"),
        (Action.DISABLE, "停用帳號"),
        (Action.ENABLE, "重新啟用帳號"),
        (Action.RESEND, "重寄啟用信"),
        (Action.PASSWORD, "寄送密碼重設信"),
        (Action.MFA, "重設雙因素驗證"),
    ], label="操作")
    role = forms.ChoiceField(choices=User.Role.choices, required=False, label="新角色")
    reason = forms.CharField(required=False, max_length=500, label="重設理由")
    verified = forms.BooleanField(required=False, label="已透過獨立管道核對對方身分")

    def clean(self):
        data = super().clean()
        if data.get("action") == self.Action.ROLE and not data.get("role"):
            self.add_error("role", "請選擇新角色。")
        if data.get("action") == self.Action.MFA and not (data.get("reason") and data.get("verified")):
            self.add_error(None, "重設雙因素驗證需要填寫理由並確認已完成身分核對。")
        return data
