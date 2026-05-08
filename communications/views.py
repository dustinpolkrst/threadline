from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from core.permissions import require_internal_workspace
from workspaces.models import WorkspaceMembership
from .models import EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel


def _require_admin(user, workspace):
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()
    if not membership or membership.role not in [WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.ADMIN]:
        raise PermissionDenied("Workspace admin access required.")
    return membership


@login_required
def email_plumbing_settings(request):
    workspace = require_internal_workspace(request.user)
    _require_admin(request.user, workspace)
    return render(
        request,
        "communications/settings.html",
        {
            "mailboxes": MailboxChannel.objects.filter(workspace=workspace),
            "messages": EmailMessage.objects.filter(workspace=workspace)[:20],
            "attempts": EmailDeliveryAttempt.objects.filter(workspace=workspace)[:20],
            "ingest_logs": EmailIngestLog.objects.filter(workspace=workspace)[:20],
        },
    )
