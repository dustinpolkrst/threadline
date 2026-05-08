from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from activity.models import ActivityEvent
from activity.services import record_event
from core.permissions import require_customer_profile
from search.services import index_comment, index_ticket
from tickets.forms import PortalCommentForm, PortalTicketForm, TicketAttachmentForm
from tickets.models import Ticket, TicketAttachment, TicketComment
from time_tracking.models import TimeEntry
from tickets.services import apply_initial_sla, mark_customer_reply


@login_required
def portal_ticket_list(request):
    profile = require_customer_profile(request.user)
    tickets = Ticket.objects.filter(workspace=profile.workspace, organization=profile.organization).select_related("contact")
    status = request.GET.get("status")
    priority = request.GET.get("priority")
    q = request.GET.get("q", "").strip()
    if status:
        tickets = tickets.filter(status=status)
    if priority:
        tickets = tickets.filter(priority=priority)
    if q:
        tickets = tickets.filter(Q(title__icontains=q) | Q(description__icontains=q))
    summary_base = Ticket.objects.filter(workspace=profile.workspace, organization=profile.organization)
    summary = {
        "open": summary_base.filter(status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).count(),
        "closed": summary_base.filter(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]).count(),
        "recent": summary_base.order_by("-updated_at")[:5],
        "by_status": summary_base.values("status").annotate(count=Count("id")),
    }
    return render(request, "customer_portal/ticket_list.html", {"tickets": tickets, "profile": profile, "summary": summary, "status": status, "priority": priority, "q": q})


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
        index_ticket(ticket)
        record_event(workspace=profile.workspace, actor=request.user, ticket=ticket, event_type="ticket.created", summary=f"Ticket created: {ticket.title}", customer_visible=True)
        return redirect("portal_ticket_detail", pk=ticket.pk)
    return render(request, "customer_portal/form.html", {"form": form, "title": "New support request"})


@login_required
def portal_ticket_detail(request, pk):
    profile = require_customer_profile(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=profile.workspace, organization=profile.organization)
    comments = ticket.comments.filter(workspace=profile.workspace, visibility=TicketComment.Visibility.PUBLIC).select_related("author")
    attachments = ticket.attachments.filter(workspace=profile.workspace, customer_visible=True)
    visible_time = TimeEntry.objects.filter(workspace=profile.workspace, ticket=ticket, customer_visible=True)
    time_total = visible_time.aggregate(total=Sum("duration_minutes"))["total"] or 0
    activity = ActivityEvent.objects.filter(workspace=profile.workspace, ticket=ticket, visibility=ActivityEvent.Visibility.CUSTOMER)
    return render(request, "customer_portal/ticket_detail.html", {"ticket": ticket, "comments": comments, "form": PortalCommentForm(), "attachment_form": TicketAttachmentForm(), "attachments": attachments, "time_total": time_total, "activity": activity})


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
        index_comment(comment)
        mark_customer_reply(ticket)
        record_event(workspace=profile.workspace, actor=request.user, ticket=ticket, event_type="comment.added", summary="Customer reply added", customer_visible=True)
    return redirect("portal_ticket_detail", pk=ticket.pk)


@login_required
def portal_upload_attachment(request, pk):
    profile = require_customer_profile(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=profile.workspace, organization=profile.organization)
    form = TicketAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        uploaded = form.cleaned_data["file"]
        attachment = form.save(commit=False)
        attachment.workspace = profile.workspace
        attachment.ticket = ticket
        attachment.uploaded_by = request.user
        attachment.display_name = uploaded.name
        attachment.content_type = getattr(uploaded, "content_type", "") or ""
        attachment.size_bytes = uploaded.size
        attachment.customer_visible = True
        attachment.save()
        record_event(workspace=profile.workspace, actor=request.user, ticket=ticket, event_type="attachment.uploaded", summary=f"Customer uploaded attachment: {attachment.display_name}", customer_visible=True)
    return redirect("portal_ticket_detail", pk=ticket.pk)


@login_required
def portal_download_attachment(request, pk, attachment_id):
    profile = require_customer_profile(request.user)
    attachment = get_object_or_404(TicketAttachment, pk=attachment_id, ticket_id=pk, workspace=profile.workspace, ticket__organization=profile.organization, customer_visible=True)
    if not attachment.file:
        raise Http404
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.display_name or attachment.file.name)


@login_required
def portal_account(request):
    profile = require_customer_profile(request.user)
    password_form = PasswordChangeForm(request.user, request.POST or None if request.POST.get("action") == "password" else None)
    if request.method == "POST":
        if request.POST.get("action") == "profile":
            profile.contact.name = request.POST.get("name", profile.contact.name)
            profile.contact.phone = request.POST.get("phone", profile.contact.phone)
            profile.contact.title = request.POST.get("title", profile.contact.title)
            profile.contact.save(update_fields=["name", "phone", "title", "updated_at"])
            return redirect("portal_account")
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                return redirect("portal_account")
    return render(request, "customer_portal/account.html", {"profile": profile, "password_form": password_form})

# Create your views here.
