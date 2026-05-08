import pytest
from datetime import timezone as dt_timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.templatetags.threadline_markdown import render_markdown
from crm.models import CRMImportJob, Contact, Organization
from customer_portal.models import CustomerProfile
from communications.models import EmailAttachment, EmailMessage, MailboxChannel
from tickets.models import Ticket, TicketAttachment
from tickets.services import add_business_minutes
from workspaces.models import BusinessHoursCalendar, Invitation, Workspace, WorkspaceMembership


@pytest.fixture
def workflow_data(db):
    User = get_user_model()
    workspace = Workspace.objects.create(name="Demo", slug="workflow")
    other_workspace = Workspace.objects.create(name="Other", slug="workflow-other")
    admin = User.objects.create_user("workflow-admin", password="password")
    agent = User.objects.create_user("workflow-agent", password="password")
    customer = User.objects.create_user("workflow-customer", password="password")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceMembership.Role.ADMIN)
    WorkspaceMembership.objects.create(workspace=workspace, user=agent, role=WorkspaceMembership.Role.AGENT)
    org = Organization.objects.create(workspace=workspace, name="Acme")
    contact = Contact.objects.create(workspace=workspace, organization=org, name="Pat", email="pat-workflow@example.com")
    CustomerProfile.objects.create(user=customer, workspace=workspace, organization=org, contact=contact)
    ticket = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Workflow ticket", status=Ticket.Status.OPEN)
    other_ticket = Ticket.objects.create(workspace=other_workspace, title="Other ticket")
    return {"workspace": workspace, "other_workspace": other_workspace, "admin": admin, "agent": agent, "customer": customer, "org": org, "contact": contact, "ticket": ticket, "other_ticket": other_ticket}


@pytest.mark.django_db
def test_ticket_attachment_download_is_workspace_scoped(client, workflow_data):
    client.login(username="workflow-agent", password="password")
    uploaded = SimpleUploadedFile("debug.txt", b"debug-data", content_type="text/plain")
    response = client.post(reverse("ticket_upload_attachment", args=[workflow_data["ticket"].pk]), {"file": uploaded})
    assert response.status_code == 302
    attachment = TicketAttachment.objects.get(workspace=workflow_data["workspace"])
    assert attachment.display_name == "debug.txt"
    download = client.get(reverse("ticket_download_attachment", args=[workflow_data["ticket"].pk, attachment.pk]))
    assert download.status_code == 200
    assert client.get(reverse("ticket_download_attachment", args=[workflow_data["other_ticket"].pk, attachment.pk])).status_code == 404


@pytest.mark.django_db
def test_email_attachment_metadata_is_workspace_scoped(workflow_data):
    mailbox = MailboxChannel.objects.create(workspace=workflow_data["workspace"], name="Support", address="support-workflow@example.com")
    email = EmailMessage.objects.create(
        workspace=workflow_data["workspace"],
        mailbox=mailbox,
        ticket=workflow_data["ticket"],
        direction=EmailMessage.Direction.INBOUND,
        status=EmailMessage.Status.STUBBED,
        message_id="attachment-message",
        sender="pat-workflow@example.com",
        recipients=["support-workflow@example.com"],
        subject="Attachment",
    )
    attachment = EmailAttachment.objects.create(workspace=workflow_data["workspace"], email_message=email, file=SimpleUploadedFile("trace.log", b"log"), display_name="trace.log", content_type="text/plain", size_bytes=3)
    assert email.attachments.get(pk=attachment.pk).workspace == workflow_data["workspace"]


@pytest.mark.django_db
def test_customer_portal_filters_and_account_update(client, workflow_data):
    Ticket.objects.create(workspace=workflow_data["workspace"], organization=workflow_data["org"], title="Closed item", status=Ticket.Status.CLOSED)
    client.login(username="workflow-customer", password="password")
    page = client.get(reverse("portal_ticket_list") + "?status=open").content.decode()
    assert "Workflow ticket" in page
    assert "Closed item" not in page
    response = client.post(reverse("portal_account"), {"action": "profile", "name": "Pat Updated", "phone": "555-0100", "title": "CTO"})
    assert response.status_code == 302
    workflow_data["contact"].refresh_from_db()
    assert workflow_data["contact"].name == "Pat Updated"
    assert workflow_data["contact"].organization == workflow_data["org"]


@pytest.mark.django_db
def test_copyable_invitation_acceptance_creates_membership(client, workflow_data):
    invite = Invitation.objects.create(
        workspace=workflow_data["workspace"],
        email="new-agent@example.com",
        invite_type=Invitation.InviteType.INTERNAL,
        role=WorkspaceMembership.Role.AGENT,
        invited_by=workflow_data["admin"],
        expires_at=timezone.now() + timezone.timedelta(days=1),
    )
    response = client.post(reverse("accept_invitation", args=[invite.token]), {"username": "new-agent", "password": "complex-password", "first_name": "New", "last_name": "Agent"})
    assert response.status_code == 302
    user = get_user_model().objects.get(username="new-agent")
    assert WorkspaceMembership.objects.filter(workspace=workflow_data["workspace"], user=user, role=WorkspaceMembership.Role.AGENT).exists()
    invite.refresh_from_db()
    assert invite.accepted_at is not None


@pytest.mark.django_db
def test_business_hours_sla_skips_closed_time(workflow_data):
    BusinessHoursCalendar.objects.create(workspace=workflow_data["workspace"], timezone="UTC")
    start = timezone.datetime(2026, 5, 8, 16, 30, tzinfo=dt_timezone.utc)
    due = add_business_minutes(workflow_data["workspace"], start, 90)
    assert due.weekday() == 0
    assert due.hour == 10
    assert due.minute == 0


@pytest.mark.django_db
def test_bulk_ticket_action_is_workspace_scoped(client, workflow_data):
    client.login(username="workflow-agent", password="password")
    response = client.post(
        reverse("ticket_bulk_action"),
        {"ticket_ids": f"{workflow_data['ticket'].pk},{workflow_data['other_ticket'].pk}", "action": "status", "status": Ticket.Status.RESOLVED},
    )
    assert response.status_code == 302
    workflow_data["ticket"].refresh_from_db()
    workflow_data["other_ticket"].refresh_from_db()
    assert workflow_data["ticket"].status == Ticket.Status.RESOLVED
    assert workflow_data["other_ticket"].status != Ticket.Status.RESOLVED


@pytest.mark.django_db
def test_csv_import_preview_and_confirm(client, workflow_data):
    client.login(username="workflow-agent", password="password")
    csv_file = SimpleUploadedFile("orgs.csv", b"name,domain\nNorthstar,northstar.example\n", content_type="text/csv")
    response = client.post(reverse("crm_import_upload"), {"import_type": CRMImportJob.ImportType.ORGANIZATIONS, "file": csv_file})
    assert response.status_code == 302
    job = CRMImportJob.objects.get(workspace=workflow_data["workspace"], filename="orgs.csv")
    assert job.rows.count() == 1
    response = client.post(reverse("crm_import_preview", args=[job.pk]))
    assert response.status_code == 302
    assert Organization.objects.filter(workspace=workflow_data["workspace"], name="Northstar").exists()


def test_markdown_renderer_sanitizes_script_tags():
    rendered = str(render_markdown("**ok** <script>alert('x')</script>"))
    assert "<strong>ok</strong>" in rendered
    assert "<script>" not in rendered
