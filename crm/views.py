from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q, Sum
import csv
import io
from activity.models import ActivityEvent
from core.permissions import require_internal_workspace
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from .forms import CRMImportUploadForm, ContactForm, OrganizationForm
from .models import CRMImportJob, CRMImportRow, Contact, Organization
from workspaces.models import BusinessHoursCalendar, Invitation, SLAPolicy, WorkspaceMembership
from workspaces.forms import BusinessHoursCalendarForm, InvitationForm, SLAPolicyForm, WorkspaceSLAForm


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
        if request.POST.get("action") == "sla_policy":
            form = SLAPolicyForm(request.POST)
            if form.is_valid():
                SLAPolicy.objects.update_or_create(workspace=workspace, priority=form.cleaned_data["priority"], defaults={
                    "first_response_target_minutes": form.cleaned_data["first_response_target_minutes"],
                    "next_response_target_minutes": form.cleaned_data["next_response_target_minutes"],
                    "resolution_target_minutes": form.cleaned_data["resolution_target_minutes"],
                })
            return redirect("team_settings")
        if request.POST.get("action") == "calendar":
            calendar, _ = BusinessHoursCalendar.objects.get_or_create(workspace=workspace)
            form = BusinessHoursCalendarForm(request.POST, instance=calendar)
            if form.is_valid():
                form.save()
            return redirect("team_settings")
        if request.POST.get("action") == "invite":
            form = InvitationForm(request.POST)
            form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
            form.fields["contact"].queryset = Contact.objects.filter(workspace=workspace)
            if form.is_valid():
                invite = form.save(commit=False)
                invite.workspace = workspace
                invite.invited_by = request.user
                invite.save()
            return redirect("team_settings")
        target = get_object_or_404(WorkspaceMembership, pk=request.POST.get("membership_id"), workspace=workspace)
        role = request.POST.get("role")
        if role in WorkspaceMembership.Role.values:
            target.role = role
            target.save(update_fields=["role"])
        return redirect("team_settings")
    memberships = WorkspaceMembership.objects.filter(workspace=workspace).select_related("user")
    customer_profiles = CustomerProfile.objects.filter(workspace=workspace).select_related("user", "organization", "contact")
    invitations = Invitation.objects.filter(workspace=workspace).select_related("organization", "contact", "invited_by")[:25]
    invitation_form = InvitationForm(initial={"expires_at": timezone.now() + timezone.timedelta(days=7), "role": WorkspaceMembership.Role.AGENT})
    invitation_form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
    invitation_form.fields["contact"].queryset = Contact.objects.filter(workspace=workspace)
    calendar, _ = BusinessHoursCalendar.objects.get_or_create(workspace=workspace)
    return render(request, "crm/team_settings.html", {
        "memberships": memberships,
        "customer_profiles": customer_profiles,
        "roles": WorkspaceMembership.Role.choices,
        "sla_form": WorkspaceSLAForm(instance=workspace),
        "sla_policy_form": SLAPolicyForm(),
        "sla_policies": SLAPolicy.objects.filter(workspace=workspace),
        "calendar_form": BusinessHoursCalendarForm(instance=calendar),
        "invitation_form": invitation_form,
        "invitations": invitations,
    })


@login_required
def crm_import_upload(request):
    workspace = require_internal_workspace(request.user)
    form = CRMImportUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        uploaded = form.cleaned_data["file"]
        job = CRMImportJob.objects.create(workspace=workspace, import_type=form.cleaned_data["import_type"], filename=uploaded.name, created_by=request.user)
        text = uploaded.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for index, row in enumerate(reader, start=2):
            errors = _validate_import_row(workspace, job.import_type, row)
            CRMImportRow.objects.create(job=job, row_number=index, data=dict(row), errors=errors)
        return redirect("crm_import_preview", pk=job.pk)
    return render(request, "crm/import_upload.html", {"form": form})


@login_required
def crm_import_preview(request, pk):
    workspace = require_internal_workspace(request.user)
    job = get_object_or_404(CRMImportJob, pk=pk, workspace=workspace)
    if request.method == "POST" and not job.rows.exclude(errors=[]).exists():
        for row in job.rows.all():
            created = _import_row(workspace, job.import_type, row.data)
            row.created_object_id = created.pk
            row.save(update_fields=["created_object_id"])
        job.status = CRMImportJob.Status.IMPORTED
        job.imported_at = timezone.now()
        job.save(update_fields=["status", "imported_at"])
        return redirect("organization_list")
    return render(request, "crm/import_preview.html", {"job": job, "rows": job.rows.all(), "has_errors": job.rows.exclude(errors=[]).exists()})


def _validate_import_row(workspace, import_type, row):
    errors = []
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS and not row.get("name"):
        errors.append("name is required")
    if import_type == CRMImportJob.ImportType.CONTACTS:
        if not row.get("email"):
            errors.append("email is required")
        if not row.get("organization"):
            errors.append("organization is required")
        elif not Organization.objects.filter(workspace=workspace, name=row.get("organization")).exists():
            errors.append("organization must already exist")
    return errors


def _import_row(workspace, import_type, row):
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS:
        organization, _ = Organization.objects.update_or_create(
            workspace=workspace,
            name=row["name"],
            defaults={"domain": row.get("domain", ""), "website": row.get("website", ""), "phone": row.get("phone", ""), "billing_email": row.get("billing_email", ""), "industry": row.get("industry", "")},
        )
        return organization
    organization = Organization.objects.get(workspace=workspace, name=row["organization"])
    contact, _ = Contact.objects.update_or_create(
        workspace=workspace,
        email=row["email"],
        defaults={"organization": organization, "name": row.get("name") or row["email"], "phone": row.get("phone", ""), "title": row.get("title", "")},
    )
    return contact

# Create your views here.
