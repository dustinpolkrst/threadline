import pytest
from datetime import timezone as dt_timezone
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.templatetags.threadline_markdown import render_markdown
from crm.models import CRMImportJob, CRMImportRow, Contact, Organization
from customer_portal.models import CustomerProfile
from communications.models import EmailAttachment, EmailMessage, MailboxChannel
from search.models import SearchDocument
from tickets.models import Ticket, TicketAttachment
from tickets.services import add_business_minutes
from workspaces.models import ApplicationStorageSettings, BusinessHoursCalendar, Invitation, Workspace, WorkspaceMembership


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


@pytest.mark.django_db
def test_csv_import_templates_are_downloadable(client, workflow_data):
    client.login(username="workflow-agent", password="password")
    response = client.get(reverse("crm_import_template", args=[CRMImportJob.ImportType.ORGANIZATIONS]))
    assert response.status_code == 200
    assert "name,domain,website,phone,billing_email" in response.content.decode()
    response = client.get(reverse("crm_import_template", args=[CRMImportJob.ImportType.CONTACTS]))
    assert response.status_code == 200
    assert "organization,name,email,phone,title,notes" in response.content.decode()


@pytest.mark.django_db
def test_csv_import_duplicate_update_and_skip(client, workflow_data):
    client.login(username="workflow-agent", password="password")
    csv_file = SimpleUploadedFile("orgs.csv", b"name,domain,phone\nAcme,acme-new.example,555-1111\n", content_type="text/csv")
    response = client.post(reverse("crm_import_upload"), {"import_type": CRMImportJob.ImportType.ORGANIZATIONS, "file": csv_file})
    assert response.status_code == 302
    job = CRMImportJob.objects.get(workspace=workflow_data["workspace"], filename="orgs.csv")
    row = job.rows.get()
    assert row.duplicate_object_id == workflow_data["org"].pk
    assert row.resolution == CRMImportRow.Resolution.UPDATE
    assert row.warnings

    response = client.post(reverse("crm_import_preview", args=[job.pk]), {"action": "confirm"})
    assert response.status_code == 302
    workflow_data["org"].refresh_from_db()
    assert workflow_data["org"].domain == "acme-new.example"
    assert workflow_data["org"].phone == "555-1111"

    csv_file = SimpleUploadedFile("contacts.csv", b"organization,name,email,phone\nAcme,Pat Updated,pat-workflow@example.com,555-2222\n", content_type="text/csv")
    client.post(reverse("crm_import_upload"), {"import_type": CRMImportJob.ImportType.CONTACTS, "file": csv_file})
    job = CRMImportJob.objects.get(workspace=workflow_data["workspace"], filename="contacts.csv")
    row = job.rows.get()
    response = client.post(reverse("crm_import_preview", args=[job.pk]), {f"resolution_{row.pk}": CRMImportRow.Resolution.SKIP, "action": "save_resolutions"})
    assert response.status_code == 302
    response = client.post(reverse("crm_import_preview", args=[job.pk]), {"action": "confirm"})
    assert response.status_code == 302
    workflow_data["contact"].refresh_from_db()
    assert workflow_data["contact"].name == "Pat"
    assert Contact.objects.filter(workspace=workflow_data["workspace"], email="pat-workflow@example.com").count() == 1


@pytest.mark.django_db
def test_csv_import_duplicate_detection_is_workspace_scoped(client, workflow_data):
    Organization.objects.create(workspace=workflow_data["other_workspace"], name="Northstar", domain="northstar.example")
    client.login(username="workflow-agent", password="password")
    csv_file = SimpleUploadedFile("orgs.csv", b"name,domain\nNorthstar,northstar.example\n", content_type="text/csv")
    client.post(reverse("crm_import_upload"), {"import_type": CRMImportJob.ImportType.ORGANIZATIONS, "file": csv_file})
    row = CRMImportJob.objects.get(workspace=workflow_data["workspace"], filename="orgs.csv").rows.get()
    assert row.duplicate_object_id is None
    assert row.resolution == CRMImportRow.Resolution.CREATE


@pytest.mark.django_db
def test_admin_can_configure_s3_storage_settings(client, workflow_data):
    client.login(username="workflow-admin", password="password")
    response = client.post(
        reverse("team_settings"),
        {
            "action": "storage",
            "backend": ApplicationStorageSettings.Backend.S3,
            "bucket_name": "threadline-media",
            "endpoint_url": "https://s3.example.com",
            "region_name": "us-east-1",
            "access_key_id": "key",
            "secret_access_key": "secret",
            "custom_domain": "",
            "addressing_style": "path",
        },
    )
    assert response.status_code == 302
    settings = ApplicationStorageSettings.objects.get(workspace=workflow_data["workspace"])
    assert settings.is_s3_enabled
    assert settings.bucket_name == "threadline-media"


@pytest.mark.django_db
def test_rebuild_search_index_and_customer_scope(client, workflow_data):
    Ticket.objects.create(workspace=workflow_data["other_workspace"], title="Other secret")
    public_comment = workflow_data["ticket"].comments.create(workspace=workflow_data["workspace"], author=workflow_data["agent"], body="Public searchable answer", visibility="public")
    workflow_data["ticket"].comments.create(workspace=workflow_data["workspace"], author=workflow_data["agent"], body="Internal searchable secret", visibility="internal")

    call_command("rebuild_search_index", "--workspace", workflow_data["workspace"].slug, "--clear")
    assert SearchDocument.objects.filter(workspace=workflow_data["workspace"], entity_type=SearchDocument.EntityType.TICKET, object_id=workflow_data["ticket"].pk).exists()
    assert SearchDocument.objects.filter(workspace=workflow_data["workspace"], entity_type=SearchDocument.EntityType.COMMENT, object_id=public_comment.pk, customer_visible=True).exists()
    assert not SearchDocument.objects.filter(title="Other secret", workspace=workflow_data["workspace"]).exists()

    client.login(username="workflow-agent", password="password")
    body = client.get(reverse("search") + "?q=searchable").content.decode()
    assert "Public" in body and "<mark>searchable</mark>" in body and "answer" in body
    assert "Internal" in body and "<mark>searchable</mark>" in body and "secret" in body

    client.logout()
    client.login(username="workflow-customer", password="password")
    body = client.get(reverse("search") + "?q=searchable").content.decode()
    assert "Public" in body and "<mark>searchable</mark>" in body and "answer" in body
    assert "Internal searchable secret" not in body
    assert "Other secret" not in body


def test_markdown_renderer_sanitizes_script_tags():
    rendered = str(render_markdown("**ok** <script>alert('x')</script>"))
    assert "<strong>ok</strong>" in rendered
    assert "<script>" not in rendered
