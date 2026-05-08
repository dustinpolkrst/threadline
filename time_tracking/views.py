from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import render
from core.permissions import require_internal_workspace
from .models import TimeEntry


@login_required
def timesheet(request):
    workspace = require_internal_workspace(request.user)
    start = timezone.now().date() - timezone.timedelta(days=7)
    entries = TimeEntry.objects.filter(workspace=workspace, user=request.user, started_at__date__gte=start).select_related("ticket", "organization")
    total = sum(entry.duration_minutes for entry in entries)
    return render(request, "time_tracking/timesheet.html", {"entries": entries, "total": total})

# Create your views here.
