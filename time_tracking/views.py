from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from activity.services import record_event
from core.pagination import paginate
from core.permissions import require_internal_workspace, require_support_workspace
from .forms import TimeEntryForm
from .models import TimeEntry
import csv


@login_required
def timesheet(request):
    workspace = require_internal_workspace(request.user)
    start = timezone.now().date() - timezone.timedelta(days=7)
    entries = TimeEntry.objects.filter(workspace=workspace, user=request.user, started_at__date__gte=start).select_related("ticket", "organization")
    totals = entries.aggregate(total=Sum("duration_minutes"), billable=Sum("duration_minutes", filter=models.Q(billable=True)))
    page_obj = paginate(request, entries, per_page=25)
    return render(request, "time_tracking/timesheet.html", {"entries": page_obj, "page_obj": page_obj, "total": totals["total"] or 0, "billable": totals["billable"] or 0})


@login_required
def time_entry_edit(request, pk):
    workspace = require_support_workspace(request.user)
    entry = get_object_or_404(TimeEntry.objects.select_related("ticket", "organization", "contact"), pk=pk, workspace=workspace)
    form = TimeEntryForm(request.POST or None, instance=entry)
    if form.is_valid():
        entry = form.save(commit=False)
        entry.workspace = workspace
        entry.customer_visible = False
        if entry.ticket:
            entry.organization = entry.ticket.organization
            entry.contact = entry.ticket.contact
        entry.save()
        if entry.ticket:
            record_event(workspace=workspace, actor=request.user, ticket=entry.ticket, event_type="time.updated", summary=f"Updated {entry.duration_minutes} minute time entry", customer_visible=False)
            return redirect("ticket_detail", pk=entry.ticket.pk)
        return redirect("timesheet")
    return render(request, "time_tracking/time_entry_form.html", {"form": form, "entry": entry})


@login_required
def time_report(request):
    workspace = require_internal_workspace(request.user)
    today = timezone.localdate()
    month = request.GET.get("month") or today.strftime("%Y-%m")
    year, month_number = [int(part) for part in month.split("-")]
    start = timezone.datetime(year, month_number, 1, tzinfo=timezone.get_current_timezone())
    if month_number == 12:
        end = timezone.datetime(year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        end = timezone.datetime(year, month_number + 1, 1, tzinfo=timezone.get_current_timezone())
    entries = TimeEntry.objects.filter(workspace=workspace, started_at__gte=start, started_at__lt=end)
    org_rows = _with_non_billable(entries.values("organization__name").annotate(total=Sum("duration_minutes"), billable=Sum("duration_minutes", filter=models.Q(billable=True))).order_by("organization__name"))
    ticket_rows = _with_non_billable(entries.values("ticket__title").annotate(total=Sum("duration_minutes"), billable=Sum("duration_minutes", filter=models.Q(billable=True))).order_by("ticket__title"))
    agent_rows = _with_non_billable(entries.values("user__username").annotate(total=Sum("duration_minutes"), billable=Sum("duration_minutes", filter=models.Q(billable=True))).order_by("user__username"))
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="threadline-time-{month}.csv"'
        writer = csv.writer(response)
        writer.writerow(["group", "name", "total_minutes", "billable_minutes", "non_billable_minutes"])
        for group, rows, key in [("organization", org_rows, "organization__name"), ("ticket", ticket_rows, "ticket__title"), ("agent", agent_rows, "user__username")]:
            for row in rows:
                billable = row["billable"] or 0
                total = row["total"] or 0
                writer.writerow([group, row[key] or "Unassigned", total, billable, total - billable])
        return response
    return render(request, "time_tracking/report.html", {"month": month, "org_rows": org_rows, "ticket_rows": ticket_rows, "agent_rows": agent_rows})


def _with_non_billable(rows):
    hydrated = []
    for row in rows:
        row["total"] = row["total"] or 0
        row["billable"] = row["billable"] or 0
        row["non_billable"] = row["total"] - row["billable"]
        hydrated.append(row)
    return hydrated
