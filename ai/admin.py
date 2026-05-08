from django.contrib import admin

from .models import AIProviderSettings, TicketAIAnalysis


@admin.register(AIProviderSettings)
class AIProviderSettingsAdmin(admin.ModelAdmin):
    list_display = ["workspace", "provider", "enabled", "zdr_only", "auto_triage_enabled", "model", "updated_at"]
    search_fields = ["workspace__name", "model"]


@admin.register(TicketAIAnalysis)
class TicketAIAnalysisAdmin(admin.ModelAdmin):
    list_display = ["ticket", "workspace", "status", "mode", "confidence", "created_at"]
    list_filter = ["status", "mode"]
    search_fields = ["ticket__title", "summary", "solution_draft"]
