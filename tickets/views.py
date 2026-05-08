from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from activity.models import ActivityEvent
from activity.services import record_event
from core.permissions import require_internal_workspace
from crm.models import Contact, Organization
from time_tracking.forms import TimeEntryForm, TimerStartForm, TimerStopForm
from time_tracking.models import ActiveTimer, TimeEntry
from .forms import CommentForm, TicketForm
from .models import Ticket, TicketComment
from .services import OPEN_STATUSES, apply_initial_sla, mark_agent_reply, mark_resolved, sla_state


@login_required
def ticket_list(request):
    workspace = require_internal_workspace(request.user)
    tickets = Ticket.objects.filter(workspace=workspace).select_related("organization", "contact", "assignee")
    queue = request.GET.get("queue", "all")
    now = timezone.now()
    if queue == "my-open":
        tickets = tickets.filter(assignee=request.user, status__in=OPEN_STATUSES)
    elif queue == "unassigned":
        tickets = tickets.filter(assignee__isnull=True, status__in=OPEN_STATUSES)
    elif queue == "sla-at-risk":
        tickets = tickets.filter(status__in=OPEN_STATUSES).filter(next_response_due_at__lte=now + timezone.timedelta(hours=1))
    elif queue == "recently-updated":
        tickets = tickets.order_by("-updated_at")
    elif queue == "waiting-on-customer":
        tickets = tickets.filter(status=Ticket.Status.PENDING)
    status = request.GET.get("status")
    if status:
        tickets = tickets.filter(status=status)
    all_tickets = Ticket.objects.filter(workspace=workspace)
    summary = {
        "total": all_tickets.count(),
        "open": all_tickets.filter(status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).count(),
        "urgent": all_tickets.filter(priority=Ticket.Priority.URGENT).count(),
        "unassigned": all_tickets.filter(assignee__isnull=True).count(),
    }
    for ticket in tickets:
        ticket.sla_state = sla_state(ticket)
    return render(request, "tickets/ticket_list.html", {"tickets": tickets, "status": status, "queue": queue, "summary": summary})


@login_required
def ticket_create(request):
    workspace = require_internal_workspace(request.user)
    form = TicketForm(request.POST or None)
    _scope_form(form, workspace)
    if form.is_valid():
        ticket = form.save(commit=False)
        ticket.workspace = workspace
        ticket.requester = request.user
        apply_initial_sla(ticket)
        ticket.save()
        record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="ticket.created", summary=f"Ticket created: {ticket.title}", customer_visible=False)
        return redirect("ticket_detail", pk=ticket.pk)
    return render(request, "tickets/form.html", {"form": form, "title": "New ticket"})


@login_required
def ticket_detail(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket.objects.select_related("organization", "contact", "assignee"), pk=pk, workspace=workspace)
    comment_form = CommentForm()
    time_form = TimeEntryForm()
    timer_start_form = TimerStartForm()
    timer_stop_form = TimerStopForm()
    comments = ticket.comments.filter(workspace=workspace).select_related("author")
    time_entries = ticket.time_entries.filter(workspace=workspace).select_related("user")
    time_total = time_entries.aggregate(total=Sum("duration_minutes"))["total"] or 0
    active_timer = ActiveTimer.objects.filter(workspace=workspace, user=request.user).select_related("ticket").first()
    activity = ticket.activity_events.filter(workspace=workspace).select_related("actor")
    ticket.sla_state = sla_state(ticket)
    return render(
        request,
        "tickets/ticket_detail.html",
        {
            "ticket": ticket,
            "comments": comments,
            "comment_form": comment_form,
            "time_form": time_form,
            "timer_start_form": timer_start_form,
            "timer_stop_form": timer_stop_form,
            "active_timer": active_timer,
            "time_entries": time_entries,
            "time_total": time_total,
            "activity": activity,
        },
    )


@login_required
def ticket_add_comment(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.workspace = workspace
        comment.ticket = ticket
        comment.author = request.user
        comment.visibility = TicketComment.Visibility.INTERNAL
        comment.save()
        record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="comment.added", summary="Comment added", customer_visible=False)
        mark_agent_reply(ticket)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_resolve(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    mark_resolved(ticket)
    record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="ticket.resolved", summary="Ticket resolved", customer_visible=False)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_add_time(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    form = TimeEntryForm(request.POST)
    if form.is_valid():
        entry = form.save(commit=False)
        entry.workspace = workspace
        entry.user = request.user
        entry.ticket = ticket
        entry.organization = ticket.organization
        entry.contact = ticket.contact
        entry.customer_visible = False
        entry.save()
        record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="time.logged", summary=f"Logged {entry.duration_minutes} minutes", customer_visible=False)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_start_timer(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    form = TimerStartForm(request.POST)
    if form.is_valid():
        ActiveTimer.objects.update_or_create(
            workspace=workspace,
            user=request.user,
            defaults={
                "ticket": ticket,
                "organization": ticket.organization,
                "contact": ticket.contact,
                "started_at": timezone.now(),
                "billable": form.cleaned_data["billable"],
                "customer_visible": False,
                "notes": form.cleaned_data["notes"],
            },
        )
        record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="timer.started", summary="Timer started", customer_visible=False)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_stop_timer(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    timer = get_object_or_404(ActiveTimer, workspace=workspace, user=request.user, ticket=ticket)
    form = TimerStopForm(request.POST)
    if form.is_valid():
        ended_at = timezone.now()
        elapsed_seconds = max(60, int((ended_at - timer.started_at).total_seconds()))
        duration_minutes = max(1, round(elapsed_seconds / 60))
        notes = form.cleaned_data["notes"].strip() or timer.notes
        entry = TimeEntry.objects.create(
            workspace=workspace,
            user=request.user,
            ticket=ticket,
            organization=timer.organization,
            contact=timer.contact,
            started_at=timer.started_at,
            ended_at=ended_at,
            duration_minutes=duration_minutes,
            billable=timer.billable,
            customer_visible=False,
            notes=notes,
        )
        timer.delete()
        record_event(workspace=workspace, actor=request.user, ticket=ticket, event_type="time.logged", summary=f"Timer logged {entry.duration_minutes} billable minutes", customer_visible=False)
    return redirect("ticket_detail", pk=ticket.pk)


def _scope_form(form, workspace):
    form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
    form.fields["contact"].queryset = Contact.objects.filter(workspace=workspace)
    user_ids = workspace.memberships.values_list("user_id", flat=True)
    form.fields["assignee"].queryset = get_user_model().objects.filter(id__in=user_ids)

# Create your views here.
