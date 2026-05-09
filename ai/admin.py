from django.contrib import admin

from .models import AIRun, AISuggestedAction, AIProviderSettings, CRMInsight, SolutionSnippet, TicketAIAnalysis, TicketReplyDraft, TimeEntrySuggestion, WorkspaceDigest


@admin.register(AIProviderSettings)
class AIProviderSettingsAdmin(admin.ModelAdmin):
    list_display = ["workspace", "provider", "enabled", "zdr_only", "auto_triage_enabled", "model", "updated_at"]
    search_fields = ["workspace__name", "model"]


@admin.register(TicketAIAnalysis)
class TicketAIAnalysisAdmin(admin.ModelAdmin):
    list_display = ["ticket", "workspace", "status", "mode", "confidence", "created_at"]
    list_filter = ["status", "mode"]
    search_fields = ["ticket__title", "summary", "solution_draft"]


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    list_display = ["workspace", "workflow", "status", "subject_type", "total_tokens", "created_at"]
    list_filter = ["workflow", "status", "privacy_mode"]
    search_fields = ["workspace__name", "subject_type"]


admin.site.register(AISuggestedAction)
admin.site.register(TicketReplyDraft)
admin.site.register(CRMInsight)
admin.site.register(TimeEntrySuggestion)
admin.site.register(WorkspaceDigest)
admin.site.register(SolutionSnippet)
