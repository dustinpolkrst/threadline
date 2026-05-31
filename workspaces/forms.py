from django import forms
from django.contrib.auth import get_user_model
from .models import BusinessHoursCalendar, Invitation, SLAPolicy, Workspace
from .theme import THEME_PRESET_CHOICES, THEME_TOKENS, preset_tokens, validate_hex_color


class WorkspaceSLAForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ["first_response_target_minutes", "next_response_target_minutes", "resolution_target_minutes"]


class WorkspaceThemeForm(forms.ModelForm):
    reset_custom_tokens = forms.BooleanField(required=False, label="Reset custom colors")

    class Meta:
        model = Workspace
        fields = ["theme_preset"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme_preset"].choices = THEME_PRESET_CHOICES
        preset_key = self.data.get(self.add_prefix("theme_preset")) if self.is_bound else self.instance.theme_preset
        base_tokens = preset_tokens(preset_key)
        saved_tokens = self.instance.theme_custom_tokens or {}
        merged_tokens = {**base_tokens, **saved_tokens}
        for token in THEME_TOKENS:
            self.fields[token.key] = forms.CharField(
                label=token.label,
                required=False,
                initial=merged_tokens[token.key],
                widget=forms.TextInput(attrs={"type": "color"}),
            )
        self.cleaned_custom_tokens = {}

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("reset_custom_tokens"):
            self.cleaned_custom_tokens = {}
            return cleaned_data

        preset_key = cleaned_data.get("theme_preset") or self.instance.theme_preset
        base_tokens = preset_tokens(preset_key)
        cleaned_tokens = {}
        for token in THEME_TOKENS:
            value = cleaned_data.get(token.key)
            if value in ("", None):
                continue
            try:
                cleaned_tokens[token.key] = validate_hex_color(str(value).strip())
            except forms.ValidationError as exc:
                self.add_error(token.key, exc)
        if self.errors:
            return cleaned_data
        self.cleaned_custom_tokens = {
            key: value
            for key, value in cleaned_tokens.items()
            if value != base_tokens[key].lower()
        }
        return cleaned_data

    def save(self, commit=True):
        workspace = super().save(commit=False)
        workspace.theme_custom_tokens = self.cleaned_custom_tokens
        if commit:
            workspace.save()
        return workspace


class SLAPolicyForm(forms.ModelForm):
    class Meta:
        model = SLAPolicy
        fields = ["priority", "first_response_target_minutes", "next_response_target_minutes", "resolution_target_minutes"]


class BusinessHoursCalendarForm(forms.ModelForm):
    class Meta:
        model = BusinessHoursCalendar
        fields = ["timezone", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "starts_at", "ends_at", "closed_dates"]
        widgets = {"starts_at": forms.TimeInput(attrs={"type": "time"}), "ends_at": forms.TimeInput(attrs={"type": "time"})}


class InvitationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=False, help_text="Optional username to reserve when accepting.")

    class Meta:
        model = Invitation
        fields = ["email", "invite_type", "role", "organization", "contact", "expires_at"]
        widgets = {"expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class AcceptInvitationForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username
