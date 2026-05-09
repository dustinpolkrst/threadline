from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q, Sum
import csv
from activity.models import ActivityEvent
from core.permissions import require_internal_workspace
from core.pagination import paginate
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from ai.models import CRMInsight
from .forms import CRMImportUploadForm, ContactForm, OrganizationForm
from .models import CRMImportJob, Contact, Organization
from .imports import confirm_import_job, create_import_job, save_import_resolutions
from .settings_handlers import build_settings_context, handle_settings_post, normalize_settings_section
from search.services import index_contact, index_organization
from workspaces.models import WorkspaceMembership


@login_required
def organization_list(request):
    workspace = require_internal_workspace(request.user)
    organizations = Organization.objects.filter(workspace=workspace).annotate(
        contact_count=Count("contacts", distinct=True),
        open_ticket_count=Count("tickets", filter=Q(tickets__status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]), distinct=True),
        total_minutes=Sum("time_entries__duration_minutes"),
    )
    page_obj = paginate(request, organizations, per_page=25)
    summary_base = Organization.objects.filter(workspace=workspace)
    summary = {
        "account_count": summary_base.count(),
        "open_ticket_count": Ticket.objects.filter(workspace=workspace, status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).count(),
        "priority_count": summary_base.filter(tier__in=[Organization.Tier.PRIORITY, Organization.Tier.ENTERPRISE]).count(),
    }
    return render(request, "crm/organization_list.html", {"organizations": page_obj, "page_obj": page_obj, "summary": summary})


@login_required
def organization_create(request):
    workspace = require_internal_workspace(request.user)
    form = OrganizationForm(request.POST or None)
    if form.is_valid():
        organization = form.save(commit=False)
        organization.workspace = workspace
        organization.save()
        index_organization(organization)
        return redirect("organization_detail", pk=organization.pk)
    return render(request, "crm/form.html", {"form": form, "title": "New organization"})


@login_required
def organization_edit(request, pk):
    workspace = require_internal_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    form = OrganizationForm(request.POST or None, instance=organization)
    if form.is_valid():
        organization = form.save()
        index_organization(organization)
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
    ai_insights = CRMInsight.objects.filter(workspace=workspace, organization=organization)[:3]
    return render(
        request,
        "crm/organization_detail.html",
        {"organization": organization, "contacts": contacts, "tickets": tickets, "status_counts": status_counts, "time_total": time_total, "activity": activity, "ai_insights": ai_insights},
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
    page_obj = paginate(request, contacts, per_page=25)
    return render(request, "crm/contact_list.html", {"contacts": page_obj, "page_obj": page_obj, "summary": summary})


@login_required
def contact_create(request):
    workspace = require_internal_workspace(request.user)
    form = ContactForm(request.POST or None)
    form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.workspace = workspace
        contact.save()
        index_contact(contact)
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
    active_section = normalize_settings_section(request.GET.get("section", "application"))
    if request.method == "POST":
        return handle_settings_post(request, workspace)
    context = build_settings_context(workspace)
    context["active_section"] = active_section
    return render(request, "crm/team_settings.html", context)


@login_required
def crm_import_upload(request):
    workspace = require_internal_workspace(request.user)
    form = CRMImportUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        job = create_import_job(workspace=workspace, import_type=form.cleaned_data["import_type"], uploaded_file=form.cleaned_data["file"], user=request.user)
        return redirect("crm_import_preview", pk=job.pk)
    return render(request, "crm/import_upload.html", {"form": form})


@login_required
def crm_import_preview(request, pk):
    workspace = require_internal_workspace(request.user)
    job = get_object_or_404(CRMImportJob, pk=pk, workspace=workspace)
    if request.method == "POST" and request.POST.get("action") == "save_resolutions":
        save_import_resolutions(job, request.POST)
        return redirect("crm_import_preview", pk=job.pk)
    if request.method == "POST" and request.POST.get("action", "confirm") == "confirm" and not job.rows.exclude(errors=[]).exists():
        confirm_import_job(workspace, job)
        return redirect("organization_list")
    return render(request, "crm/import_preview.html", {"job": job, "rows": job.rows.all(), "has_errors": job.rows.exclude(errors=[]).exists()})


@login_required
def crm_import_template(request, import_type):
    require_internal_workspace(request.user)
    headers = _template_headers(import_type)
    if not headers:
        return HttpResponse("Unknown import template.", status=404)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="threadline-{import_type}-template.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    return response


def _template_headers(import_type):
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS:
        return ["name", "domain", "website", "phone", "billing_email", "account_owner", "status", "tier", "industry", "employee_count", "annual_revenue", "address", "renewal_date", "health_score", "notes"]
    if import_type == CRMImportJob.ImportType.CONTACTS:
        return ["organization", "name", "email", "phone", "title", "notes"]
    return None
