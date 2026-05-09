from django.contrib import admin
from .models import ActiveTimer, TimeEntry

admin.site.register(TimeEntry)
admin.site.register(ActiveTimer)
