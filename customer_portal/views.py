from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from activity.models import ActivityEvent
from activity.services import record_event
from core.permissions import require_customer_profile
from tickets.forms import PortalCommentForm, PortalTicketForm
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from tickets.services import apply_initial_sla, mark_customer_reply


@login_required
def portal_ticket_list(request):
    profile = require_customer_profile(request.user)
    tickets = Ticket.objects.filter(workspace=profile.workspace, organization=profile.organization).select_related("contact")
    return render(request, "customer_portal/ticket_list.html", {"tickets": tickets, "profile": profile})


@login_required
def portal_ticket_create(request):
    profile = require_customer_profile(request.user)
    form = PortalTicketForm(request.POST or None)
    if form.is_valid():
        ticket = form.save(commit=False)
        ticket.workspace = profile.workspace
        ticket.organization = profile.organization
        ticket.contact = profile.contact
        ticket.requester = request.user
        ticket.source = Ticket.Source.PORTAL
        apply_initial_sla(ticket)
        ticket.save()
        record_event(workspace=profile.workspace, actor=request.user, ticket=ticket, event_type="ticket.created", summary=f"Ticket created: {ticket.title}", customer_visible=True)
        return redirect("portal_ticket_detail", pk=ticket.pk)
    return render(request, "customer_portal/form.html", {"form": form, "title": "New support request"})


@login_required
def portal_ticket_detail(request, pk):
    profile = require_customer_profile(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=profile.workspace, organization=profile.organization)
    comments = ticket.comments.filter(workspace=profile.workspace, visibility=TicketComment.Visibility.PUBLIC).select_related("author")
    visible_time = TimeEntry.objects.filter(workspace=profile.workspace, ticket=ticket, customer_visible=True)
    time_total = visible_time.aggregate(total=Sum("duration_minutes"))["total"] or 0
    activity = ActivityEvent.objects.filter(workspace=profile.workspace, ticket=ticket, visibility=ActivityEvent.Visibility.CUSTOMER)
    return render(request, "customer_portal/ticket_detail.html", {"ticket": ticket, "comments": comments, "form": PortalCommentForm(), "time_total": time_total, "activity": activity})


@login_required
def portal_ticket_reply(request, pk):
    profile = require_customer_profile(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=profile.workspace, organization=profile.organization)
    form = PortalCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.workspace = profile.workspace
        comment.ticket = ticket
        comment.author = request.user
        comment.visibility = TicketComment.Visibility.PUBLIC
        comment.save()
        mark_customer_reply(ticket)
        record_event(workspace=profile.workspace, actor=request.user, ticket=ticket, event_type="comment.added", summary="Customer reply added", customer_visible=True)
    return redirect("portal_ticket_detail", pk=ticket.pk)

# Create your views here.
