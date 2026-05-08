from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from activity.models import ActivityEvent
from core.permissions import customer_profile_for, require_internal_workspace
from tickets.models import Ticket
from time_tracking.models import TimeEntry


@login_required
def dashboard(request):
    if customer_profile_for(request.user):
        return redirect("portal_ticket_list")
    workspace = require_internal_workspace(request.user)
    tickets = Ticket.objects.filter(workspace=workspace).select_related("organization", "contact", "assignee")[:12]
    status_counts = Ticket.objects.filter(workspace=workspace).values("status").annotate(count=Count("id"))
    time_total = TimeEntry.objects.filter(workspace=workspace).aggregate(total=Sum("duration_minutes"))["total"] or 0
    activity = ActivityEvent.objects.filter(workspace=workspace).select_related("ticket", "organization", "actor")[:12]
    return render(request, "core/dashboard.html", {"workspace": workspace, "tickets": tickets, "status_counts": status_counts, "time_total": time_total, "activity": activity})

# Create your views here.
