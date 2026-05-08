from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from activity.models import ActivityEvent
from core.permissions import require_internal_workspace
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from .forms import ContactForm, OrganizationForm
from .models import Contact, Organization


@login_required
def organization_list(request):
    workspace = require_internal_workspace(request.user)
    organizations = Organization.objects.filter(workspace=workspace)
    return render(request, "crm/organization_list.html", {"organizations": organizations})


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
def organization_detail(request, pk):
    workspace = require_internal_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    tickets = Ticket.objects.filter(workspace=workspace, organization=organization)
    time_total = TimeEntry.objects.filter(workspace=workspace, organization=organization).aggregate(total=Sum("duration_minutes"))["total"] or 0
    activity = ActivityEvent.objects.filter(workspace=workspace, organization=organization)[:15]
    return render(request, "crm/organization_detail.html", {"organization": organization, "tickets": tickets, "time_total": time_total, "activity": activity})


@login_required
def contact_list(request):
    workspace = require_internal_workspace(request.user)
    contacts = Contact.objects.filter(workspace=workspace).select_related("organization")
    return render(request, "crm/contact_list.html", {"contacts": contacts})


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
    comments = TicketComment.objects.filter(workspace=workspace, ticket__contact=contact, visibility=TicketComment.Visibility.PUBLIC).select_related("ticket", "author")[:20]
    time_total = TimeEntry.objects.filter(workspace=workspace, contact=contact).aggregate(total=Sum("duration_minutes"))["total"] or 0
    return render(request, "crm/contact_detail.html", {"contact": contact, "tickets": tickets, "comments": comments, "time_total": time_total})

# Create your views here.
