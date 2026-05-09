from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from ai.client import OpenRouterError, send_chat_completion
from ai.forms import AIProviderSettingsForm
from ai.services import get_ai_settings
from customer_portal.models import CustomerProfile
from crm.models import Contact, Organization
from workspaces.forms import ApplicationStorageSettingsForm, BusinessHoursCalendarForm, InvitationForm, SLAPolicyForm, WorkspaceSLAForm
from workspaces.models import ApplicationStorageSettings, BusinessHoursCalendar, Invitation, SLAPolicy, WorkspaceMembership


SETTINGS_SECTIONS = ["application", "ai", "team", "sla", "invitations", "users"]


def normalize_settings_section(section):
    return section if section in SETTINGS_SECTIONS else "application"


def handle_settings_post(request, workspace):
    action = request.POST.get("action")
    if action == "sla":
        form = WorkspaceSLAForm(request.POST, instance=workspace)
        if form.is_valid():
            form.save()
        return settings_redirect("sla")
    if action == "sla_policy":
        form = SLAPolicyForm(request.POST)
        if form.is_valid():
            SLAPolicy.objects.update_or_create(
                workspace=workspace,
                priority=form.cleaned_data["priority"],
                defaults={
                    "first_response_target_minutes": form.cleaned_data["first_response_target_minutes"],
                    "next_response_target_minutes": form.cleaned_data["next_response_target_minutes"],
                    "resolution_target_minutes": form.cleaned_data["resolution_target_minutes"],
                },
            )
        return settings_redirect("sla")
    if action == "calendar":
        calendar, _ = BusinessHoursCalendar.objects.get_or_create(workspace=workspace)
        form = BusinessHoursCalendarForm(request.POST, instance=calendar)
        if form.is_valid():
            form.save()
        return settings_redirect("sla")
    if action == "invite":
        form = InvitationForm(request.POST)
        _scope_invitation_form(form, workspace)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.workspace = workspace
            invite.invited_by = request.user
            invite.save()
        return settings_redirect("invitations")
    if action == "storage":
        storage_settings, _ = ApplicationStorageSettings.objects.get_or_create(workspace=workspace)
        form = ApplicationStorageSettingsForm(request.POST, instance=storage_settings)
        if form.is_valid():
            form.save()
        return settings_redirect("application")
    if action == "ai":
        ai_settings = get_ai_settings(workspace)
        form = AIProviderSettingsForm(request.POST, instance=ai_settings)
        if form.is_valid():
            form.save()
        return settings_redirect("ai")
    if action == "ai_test":
        return _handle_ai_test(request, workspace)
    target = get_object_or_404(WorkspaceMembership, pk=request.POST.get("membership_id"), workspace=workspace)
    role = request.POST.get("role")
    if role in WorkspaceMembership.Role.values:
        target.role = role
        target.save(update_fields=["role"])
    return settings_redirect("users")


def build_settings_context(workspace):
    invitation_form = InvitationForm(initial={"expires_at": timezone.now() + timezone.timedelta(days=7), "role": WorkspaceMembership.Role.AGENT})
    _scope_invitation_form(invitation_form, workspace)
    calendar, _ = BusinessHoursCalendar.objects.get_or_create(workspace=workspace)
    storage_settings, _ = ApplicationStorageSettings.objects.get_or_create(workspace=workspace)
    ai_settings = get_ai_settings(workspace)
    return {
        "memberships": WorkspaceMembership.objects.filter(workspace=workspace).select_related("user"),
        "customer_profiles": CustomerProfile.objects.filter(workspace=workspace).select_related("user", "organization", "contact"),
        "roles": WorkspaceMembership.Role.choices,
        "sla_form": WorkspaceSLAForm(instance=workspace),
        "sla_policy_form": SLAPolicyForm(),
        "sla_policies": SLAPolicy.objects.filter(workspace=workspace),
        "calendar_form": BusinessHoursCalendarForm(instance=calendar),
        "invitation_form": invitation_form,
        "invitations": Invitation.objects.filter(workspace=workspace).select_related("organization", "contact", "invited_by")[:25],
        "storage_form": ApplicationStorageSettingsForm(instance=storage_settings),
        "storage_settings": storage_settings,
        "ai_form": AIProviderSettingsForm(instance=ai_settings),
        "ai_settings": ai_settings,
    }


def settings_redirect(section):
    return redirect(f"{reverse('team_settings')}?section={section}")


def _scope_invitation_form(form, workspace):
    form.fields["organization"].queryset = Organization.objects.filter(workspace=workspace)
    form.fields["contact"].queryset = Contact.objects.filter(workspace=workspace)


def _handle_ai_test(request, workspace):
    ai_settings = get_ai_settings(workspace)
    form = AIProviderSettingsForm(request.POST, instance=ai_settings)
    if form.is_valid():
        ai_settings = form.save()
    try:
        response = send_chat_completion(
            ai_settings,
            [
                {"role": "system", "content": "Return a small JSON health response."},
                {"role": "user", "content": "Threadline AI provider health check."},
            ],
            max_tokens=200,
            structured=False,
        )
        ai_settings.last_test_status = "ok"
        ai_settings.last_test_message = f"Provider returned {response.get('model', 'unknown model')}"
    except OpenRouterError as exc:
        ai_settings.last_test_status = "failed"
        ai_settings.last_test_message = str(exc)[:500]
    ai_settings.last_tested_at = timezone.now()
    ai_settings.save(update_fields=["last_test_status", "last_test_message", "last_tested_at", "updated_at"])
    return settings_redirect("ai")
