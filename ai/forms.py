from django import forms

from .models import AIProviderSettings


class AIProviderSettingsForm(forms.ModelForm):
    api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current OpenRouter API key.",
    )

    class Meta:
        model = AIProviderSettings
        fields = ["enabled", "api_key", "model", "zdr_only", "auto_triage_enabled", "ticket_drafts_enabled", "crm_insights_enabled", "time_suggestions_enabled", "digest_enabled", "max_historical_tickets"]
        help_texts = {
            "zdr_only": "Required by default for client ticket history.",
            "auto_triage_enabled": "Allows users to apply AI triage suggestions after generation.",
            "ticket_drafts_enabled": "Allows internal ticket reply drafts and next-action suggestions.",
            "crm_insights_enabled": "Allows account and contact support briefings.",
            "time_suggestions_enabled": "Allows draft time-entry suggestions from ticket activity.",
            "digest_enabled": "Allows workspace-level AI digests for admins.",
            "max_historical_tickets": "Bounded same-client ticket history included in prompts.",
        }

    def clean_zdr_only(self):
        return True

    def clean_max_historical_tickets(self):
        value = self.cleaned_data["max_historical_tickets"]
        return max(0, min(value, 20))

    def save(self, commit=True):
        instance = super().save(commit=False)
        api_key = self.cleaned_data.get("api_key", "").strip()
        if api_key:
            instance.set_api_key(api_key)
        elif instance.pk:
            existing = AIProviderSettings.objects.get(pk=instance.pk)
            instance.encrypted_api_key = existing.encrypted_api_key
            instance.api_key = existing.api_key
        if commit:
            instance.save()
        return instance
