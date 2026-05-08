from django.contrib import admin
from .models import ApplicationStorageSettings, BusinessHoursCalendar, Invitation, SLAPolicy, Workspace, WorkspaceMembership

admin.site.register(ApplicationStorageSettings)
admin.site.register(Workspace)
admin.site.register(WorkspaceMembership)
admin.site.register(SLAPolicy)
admin.site.register(BusinessHoursCalendar)
admin.site.register(Invitation)

# Register your models here.
