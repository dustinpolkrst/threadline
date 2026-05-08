from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q, Sum
from activity.models import ActivityEvent
from core.permissions import require_internal_workspace
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from .forms import ContactForm, OrganizationForm
from .models import Contact, Organization
from workspaces.models import WorkspaceMembership
from workspaces.forms import WorkspaceSLAForm


@login_required
def organization_list(request):
    workspace = require_internal_workspace(request.user)
    organizations = Organization.objects.filter(workspace=workspace).annotate(
        contact_count=Count("contacts", distinct=True),
        open_ticket_count=Count("tickets", filter=Q(tickets__status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]), distinct=True),
        total_minutes=Sum("time_entries__duration_minutes"),
    )
    rows = list(organizations)
    summary = {
        "account_count": len(rows),
        "open_ticket_count": sum(row.open_ticket_count for row in rows),
        "priority_count": sum(1 for row in rows if row.tier in [Organization.Tier.PRIORITY, Organization.Tier.ENTERPRISE]),
    }
    return render(request, "crm/organization_list.html", {"organizations": rows, "summary": summary})


@login_required
def organization_create(request):
    workspace = require_internal_workspace(request.user)
    form = OrganizationForm(request.POST or None)
    if form.is_valid():
        organization = form.save(commit=False)
        organization.workspace = workspace
        organization.save()
        return redirect("organization_detail", pk=organization.pk)
    return render(request, "crm/form.html", {"form": form, "title": "New organization"})


@login_required
def organization_edit(request, pk):
    workspace = require_internal_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    form = OrganizationForm(request.POST or None, instance=organization)
    if form.is_valid():
        form.save()
        return redirect("organization_detail", pk=organization.pk)
    return render(request, "crm/form.html", {"form": form, "title": f"Edit {organization.name}"})


@login_required
def organization_detail(request, pk):
    workspace = require_internal_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    tickets = Ticket.objects.filter(workspace=workspace, organization=organization)
    contacts = organization.contacts.filter(workspace=workspace)
    status_counts = tickets.values("status").annotate(count=Count("id"))
    time_total = TimeEntry.objects.filter(workspace=workspace, organization=organization).aggregate(total=Sum("duration_minutes"))["total"] or 0
    activity = ActivityEvent.objects.filter(workspace=workspace, organization=organization)[:15]
    return render(
        request,
        "crm/organization_detail.html",
        {"organization": organization, "contacts": contacts, "tickets": tickets, "status_counts": status_counts, "time_total": time_total, "activity": activity},
    )


@login_required
def contact_list(request):
    workspace = require_internal_workspace(request.user)
    contacts = Contact.objects.filter(workspace=workspace).select_related("organization")
    summary = {
        "total": contacts.count(),
        "organizations": Organization.objects.filter(workspace=workspace).count(),
        "with_phone": contacts.exclude(phone="").count(),
    }
    return render(request, "crm/contact_list.html", {"contacts": contacts, "summary": summary})


@login_required
def contact_create(request):
    workspace = require_internal_workspace(request.user)
    form = ContactForm(request.POST or None)
    form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.workspace = workspace
        contact.save()
        return redirect("contact_detail", pk=contact.pk)
    return render(request, "crm/form.html", {"form": form, "title": "New contact"})


@login_required
def contact_detail(request, pk):
    workspace = require_internal_workspace(request.user)
    contact = get_object_or_404(Contact, pk=pk, workspace=workspace)
    tickets = Ticket.objects.filter(workspace=workspace, contact=contact)
    comments = TicketComment.objects.filter(workspace=workspace, ticket__contact=contact).select_related("ticket", "author")[:20]
    time_total = TimeEntry.objects.filter(workspace=workspace, contact=contact).aggregate(total=Sum("duration_minutes"))["total"] or 0
    return render(request, "crm/contact_detail.html", {"contact": contact, "tickets": tickets, "comments": comments, "time_total": time_total})


@login_required
def team_settings(request):
    workspace = require_internal_workspace(request.user)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
    if not membership or membership.role not in [WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.ADMIN]:
        raise PermissionDenied("Workspace admin access required.")
    if request.method == "POST":
        if request.POST.get("action") == "sla":
            form = WorkspaceSLAForm(request.POST, instance=workspace)
            if form.is_valid():
                form.save()
            return redirect("team_settings")
        target = get_object_or_404(WorkspaceMembership, pk=request.POST.get("membership_id"), workspace=workspace)
        role = request.POST.get("role")
        if role in WorkspaceMembership.Role.values:
            target.role = role
            target.save(update_fields=["role"])
        return redirect("team_settings")
    memberships = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user")
    customer_profiles = CustomerProfile.objects.filter(workspace=workspace).select_related("user", "organization", "contact")
    return render(request, "crm/team_settings.html", {"memberships": memberships, "customer_profiles": customer_profiles, "roles": WorkspaceMembership.Role.choices, "sla_form": WorkspaceSLAForm(instance=workspace)})

# Create your views here.
