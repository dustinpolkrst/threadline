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
        fields = [
            "enabled",
            "api_key",
            "model",
            "zdr_only",
            "auto_triage_enabled",
            "ticket_drafts_enabled",
            "reply_composer_enabled",
            "solution_memory_enabled",
            "crm_insights_enabled",
            "time_suggestions_enabled",
            "queue_intelligence_enabled",
            "digest_enabled",
            "max_historical_tickets",
            "monthly_token_cap",
            "monthly_run_cap",
            "generation_retention_days",
        ]
        help_texts = {
            "zdr_only": "Required by default for client ticket history.",
            "auto_triage_enabled": "Allows users to apply AI triage suggestions after generation.",
            "ticket_drafts_enabled": "Allows internal ticket reply drafts and next-action suggestions.",
            "reply_composer_enabled": "Allows agents to generate and transform human-approved customer reply drafts.",
            "solution_memory_enabled": "Allows approved reusable solution snippets to be generated and searched.",
            "crm_insights_enabled": "Allows account and contact support briefings.",
            "time_suggestions_enabled": "Allows draft time-entry suggestions from ticket activity.",
            "queue_intelligence_enabled": "Allows dashboard recommendations for urgent, stale, duplicate, and SLA-risk tickets.",
            "digest_enabled": "Allows workspace-level AI digests for admins.",
            "max_historical_tickets": "Bounded same-client ticket history included in prompts.",
            "monthly_token_cap": "Maximum generated tokens per calendar month. Use 0 for no cap.",
            "monthly_run_cap": "Maximum provider-backed AI runs per calendar month. Use 0 for no cap.",
            "generation_retention_days": "Days to keep generated outputs and prompt context. Use 0 to retain indefinitely.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["monthly_token_cap", "monthly_run_cap", "generation_retention_days"]:
            self.fields[field_name].required = False

    def clean_zdr_only(self):
        return True

    def clean_monthly_token_cap(self):
        value = self.cleaned_data.get("monthly_token_cap")
        if value is None:
            return self.instance.monthly_token_cap if self.instance.pk else 0
        return value

    def clean_monthly_run_cap(self):
        value = self.cleaned_data.get("monthly_run_cap")
        if value is None:
            return self.instance.monthly_run_cap if self.instance.pk else 0
        return value

    def clean_max_historical_tickets(self):
        value = self.cleaned_data["max_historical_tickets"]
        return max(0, min(value, 20))

    def clean_generation_retention_days(self):
        value = self.cleaned_data.get("generation_retention_days")
        if value is None:
            value = self.instance.generation_retention_days if self.instance.pk else 90
        return max(0, min(value, 3650))

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
