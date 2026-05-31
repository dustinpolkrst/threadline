from django.contrib import admin
from .models import BusinessHoursCalendar, Invitation, SLAPolicy, Workspace, WorkspaceMembership


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "theme_preset", "created_at"]
    fields = ["name", "slug", "theme_preset", "theme_custom_tokens", "first_response_target_minutes", "next_response_target_minutes", "resolution_target_minutes"]


admin.site.register(WorkspaceMembership)
admin.site.register(SLAPolicy)
admin.site.register(BusinessHoursCalendar)
admin.site.register(Invitation)
