import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from communications.models import EmailIngestLog, EmailMessage, MailboxChannel
from communications.services import append_reply_from_inbound_email_stub, create_ticket_from_inbound_email_stub, queue_outbound_ticket_reply_stub
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket
from time_tracking.models import TimeEntry
from workspaces.models import BusinessHoursCalendar, Invitation, Workspace, WorkspaceMembership


@pytest.fixture
def support_data(db):
    User = get_user_model()
    workspace = Workspace.objects.create(name="Demo", slug="demo")
    other_workspace = Workspace.objects.create(name="Other", slug="other")
    agent = User.objects.create_user("agent", password="password")
    admin = User.objects.create_user("admin", password="password")
    customer = User.objects.create_user("customer", password="password")
    WorkspaceMembership.objects.create(workspace=workspace, user=agent, role=WorkspaceMembership.Role.AGENT)
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceMembership.Role.ADMIN)
    org = Organization.objects.create(workspace=workspace, name="Acme")
    contact = Contact.objects.create(workspace=workspace, organization=org, name="Pat", email="pat@example.com")
    CustomerProfile.objects.create(user=customer, workspace=workspace, organization=org, contact=contact)
    ticket = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Open", status=Ticket.Status.OPEN, next_response_due_at=timezone.now() - timezone.timedelta(minutes=5))
    assigned = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Mine", status=Ticket.Status.OPEN, assignee=agent)
    pending = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Waiting", status=Ticket.Status.PENDING, waiting_since=timezone.now())
    other_ticket = Ticket.objects.create(workspace=other_workspace, title="Other")
    mailbox = MailboxChannel.objects.create(workspace=workspace, name="Support", address="support@example.com")
    return {"workspace": workspace, "other_workspace": other_workspace, "agent": agent, "admin": admin, "customer": customer, "org": org, "contact": contact, "ticket": ticket, "assigned": assigned, "pending": pending, "other_ticket": other_ticket, "mailbox": mailbox}


@pytest.mark.django_db
def test_stub_inbound_email_creates_ticket_and_deduplicates(support_data):
    email, ticket, created = create_ticket_from_inbound_email_stub(
        workspace=support_data["workspace"],
        mailbox=support_data["mailbox"],
        message_id="msg-1",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject="Email issue",
        text_body="Help",
    )
    duplicate, duplicate_ticket, duplicate_created = create_ticket_from_inbound_email_stub(
        workspace=support_data["workspace"],
        mailbox=support_data["mailbox"],
        message_id="msg-1",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject="Email issue",
        text_body="Help",
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate.pk == email.pk
    assert duplicate_ticket.pk == ticket.pk
    assert EmailIngestLog.objects.filter(workspace=support_data["workspace"], status=EmailIngestLog.Status.DUPLICATE).exists()


@pytest.mark.django_db
def test_stub_inbound_reply_and_outbound_queue_records(support_data):
    email, comment, created = append_reply_from_inbound_email_stub(
        workspace=support_data["workspace"],
        ticket=support_data["ticket"],
        mailbox=support_data["mailbox"],
        message_id="reply-1",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject="Re: Open",
        text_body="More info",
    )
    outbound = queue_outbound_ticket_reply_stub(
        workspace=support_data["workspace"],
        ticket=support_data["ticket"],
        sender="support@example.com",
        recipients=["pat@example.com"],
        subject="Re: Open",
        text_body="Thanks",
    )
    assert created is True
    assert email.comment == comment
    assert outbound.delivery_attempts.filter(status="stubbed").exists()


@pytest.mark.django_db
def test_saved_ticket_queues(client, support_data):
    client.login(username="agent", password="password")
    assert "Mine" in client.get(reverse("ticket_list") + "?queue=my-open").content.decode()
    unassigned = client.get(reverse("ticket_list") + "?queue=unassigned").content.decode()
    assert "Open" in unassigned
    assert "Mine" not in unassigned
    assert "Open" in client.get(reverse("ticket_list") + "?queue=sla-at-risk").content.decode()
    assert "Waiting" in client.get(reverse("ticket_list") + "?queue=waiting-on-customer").content.decode()


@pytest.mark.django_db
def test_customer_and_agent_cannot_access_admin_settings(client, support_data):
    client.login(username="customer", password="password")
    assert client.get(reverse("email_plumbing_settings")).status_code == 403
    client.logout()
    client.login(username="agent", password="password")
    assert client.get(reverse("team_settings")).status_code == 403
    client.logout()
    client.login(username="admin", password="password")
    assert client.get(reverse("team_settings")).status_code == 200
    assert client.get(reverse("email_plumbing_settings")).status_code == 200


@pytest.mark.django_db
def test_settings_application_storage_tab_exposes_s3_setup(client, support_data):
    client.login(username="admin", password="password")
    response = client.get(reverse("team_settings"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Attachment storage" in body
    assert "S3-compatible provider" in body
    assert "Bucket and endpoint" in body
    assert "Private objects stay behind Django permission checks" in body
    assert "bucket_name" in body
    assert "endpoint_url" in body
    assert "secret_access_key" in body

    response = client.post(
        reverse("team_settings"),
        {
            "action": "storage",
            "backend": "s3",
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
    assert response["Location"].endswith("?section=application")


@pytest.mark.django_db
def test_settings_sections_render_redesigned_admin_panels(client, support_data):
    client.login(username="admin", password="password")
    sections = {
        "team": ["Internal members", "Customer portal users", "Open invites"],
        "sla": ["Default response targets", "Priority policies", "Business hours"],
        "invitations": ["Create invite link", "Recent invitations", "Links expire based on the date above"],
        "users": ["Access management", "Current role", "Portal users"],
    }
    for section, expected in sections.items():
        response = client.get(f"{reverse('team_settings')}?section={section}")
        body = response.content.decode()
        assert response.status_code == 200
        for text in expected:
            assert text in body


@pytest.mark.django_db
def test_admin_can_update_workspace_sla_targets(client, support_data):
    client.login(username="admin", password="password")
    response = client.post(
        reverse("team_settings"),
        {
            "action": "sla",
            "first_response_target_minutes": "30",
            "next_response_target_minutes": "60",
            "resolution_target_minutes": "240",
        },
    )
    assert response.status_code == 302
    support_data["workspace"].refresh_from_db()
    assert support_data["workspace"].first_response_target_minutes == 30
    assert support_data["workspace"].next_response_target_minutes == 60
    assert support_data["workspace"].resolution_target_minutes == 240


@pytest.mark.django_db
def test_settings_post_actions_redirect_to_active_sections(client, support_data):
    client.login(username="admin", password="password")
    response = client.post(
        reverse("team_settings"),
        {
            "action": "calendar",
            "timezone": "UTC",
            "monday": "on",
            "tuesday": "on",
            "wednesday": "on",
            "thursday": "on",
            "friday": "on",
            "starts_at": "08:30",
            "ends_at": "17:30",
            "closed_dates": "[]",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("?section=sla")
    assert BusinessHoursCalendar.objects.filter(workspace=support_data["workspace"], starts_at="08:30").exists()

    response = client.post(
        reverse("team_settings"),
        {
            "action": "invite",
            "email": "new-agent@example.com",
            "invite_type": Invitation.InviteType.INTERNAL,
            "role": WorkspaceMembership.Role.AGENT,
            "organization": "",
            "contact": "",
            "expires_at": (timezone.now() + timezone.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            "username": "",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("?section=invitations")

    membership = WorkspaceMembership.objects.get(workspace=support_data["workspace"], user=support_data["agent"])
    response = client.post(
        reverse("team_settings"),
        {"membership_id": str(membership.pk), "role": WorkspaceMembership.Role.VIEWER},
    )
    assert response.status_code == 302
    assert response["Location"].endswith("?section=users")
    membership.refresh_from_db()
    assert membership.role == WorkspaceMembership.Role.VIEWER


@pytest.mark.django_db
def test_time_report_totals_and_csv_scope(client, support_data):
    TimeEntry.objects.create(workspace=support_data["workspace"], user=support_data["agent"], ticket=support_data["ticket"], organization=support_data["org"], started_at=timezone.now(), duration_minutes=30, billable=True)
    TimeEntry.objects.create(workspace=support_data["workspace"], user=support_data["agent"], ticket=support_data["ticket"], organization=support_data["org"], started_at=timezone.now(), duration_minutes=15, billable=False)
    TimeEntry.objects.create(workspace=support_data["other_workspace"], user=support_data["agent"], ticket=support_data["other_ticket"], started_at=timezone.now(), duration_minutes=999, billable=True)
    client.login(username="agent", password="password")
    page = client.get(reverse("time_report")).content.decode()
    assert "45m" in page
    csv_response = client.get(reverse("time_report") + "?format=csv")
    body = csv_response.content.decode()
    assert "Acme" in body
    assert "999" not in body
