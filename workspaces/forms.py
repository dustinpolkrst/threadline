from django import forms
from django.contrib.auth import get_user_model
from .models import BusinessHoursCalendar, Invitation, SLAPolicy, Workspace


class WorkspaceSLAForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ["first_response_target_minutes", "next_response_target_minutes", "resolution_target_minutes"]


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
