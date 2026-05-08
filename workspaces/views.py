from django.contrib.auth import get_user_model, login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from customer_portal.models import CustomerProfile
from .forms import AcceptInvitationForm
from .models import Invitation, WorkspaceMembership


def accept_invitation(request, token):
    invitation = get_object_or_404(Invitation, token=token)
    form = AcceptInvitationForm(request.POST or None)
    if invitation.is_expired or invitation.is_accepted:
        return render(request, "workspaces/invitation_invalid.html", {"invitation": invitation})
    if form.is_valid():
        user = get_user_model().objects.create_user(
            username=form.cleaned_data["username"],
            email=invitation.email,
            password=form.cleaned_data["password"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        if invitation.invite_type == Invitation.InviteType.INTERNAL:
            WorkspaceMembership.objects.create(workspace=invitation.workspace, user=user, role=invitation.role or WorkspaceMembership.Role.AGENT)
        else:
            CustomerProfile.objects.create(user=user, workspace=invitation.workspace, organization=invitation.organization, contact=invitation.contact)
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_by", "accepted_at"])
        login(request, user)
        return redirect("dashboard")
    return render(request, "workspaces/accept_invitation.html", {"invitation": invitation, "form": form})
