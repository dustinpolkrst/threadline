import pytest
from activity.models import ActivityEvent
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from communications.models import EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel
from communications import services as email_services
from communications.services import append_reply_from_inbound_email_stub, create_ticket_from_inbound_email_stub, queue_outbound_ticket_reply_stub
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from search.models import SearchDocument
from tickets.models import Ticket, TicketComment
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
def test_real_inbound_email_creates_ticket_deduplicates_and_stores_attachment(support_data):
    email, ticket, created = email_services.process_inbound_email(
        workspace=support_data["workspace"],
        mailbox=support_data["mailbox"],
        message_id="<real-msg-1@example.com>",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject="Production is down",
        text_body="Please help",
        attachments=[
            {
                "filename": "trace.txt",
                "content": ContentFile(b"stack trace", name="trace.txt"),
                "content_type": "text/plain",
            }
        ],
    )
    duplicate, duplicate_ticket, duplicate_created = email_services.process_inbound_email(
        workspace=support_data["workspace"],
        mailbox=support_data["mailbox"],
        message_id="<real-msg-1@example.com>",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject="Production is down",
        text_body="Please help",
    )
    assert created is True
    assert email.status == EmailMessage.Status.PROCESSED
    assert ticket.source == Ticket.Source.EMAIL
    assert email.attachments.filter(display_name="trace.txt", content_type="text/plain").exists()
    assert duplicate_created is False
    assert duplicate.pk == email.pk
    assert duplicate_ticket.pk == ticket.pk
    assert EmailIngestLog.objects.filter(workspace=support_data["workspace"], status=EmailIngestLog.Status.DUPLICATE).exists()


@pytest.mark.django_db
def test_real_inbound_email_threads_reply_from_ticket_reference(support_data):
    email, comment, created = email_services.process_inbound_email(
        workspace=support_data["workspace"],
        mailbox=support_data["mailbox"],
        message_id="<real-reply-1@example.com>",
        sender="pat@example.com",
        recipients=["support@example.com"],
        subject=email_services.ticket_email_subject(support_data["ticket"], "Re: Open"),
        text_body="Here is the requested detail",
    )
    assert created is True
    assert email.ticket == support_data["ticket"]
    assert comment.ticket == support_data["ticket"]
    assert comment.visibility == "public"
    assert Ticket.objects.filter(workspace=support_data["workspace"], title="Re: Open").count() == 0


@pytest.mark.django_db
def test_queued_outbound_email_sends_with_delivery_attempt(settings, support_data):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    support_data["mailbox"].status = MailboxChannel.Status.READY
    support_data["mailbox"].outbound_enabled = True
    support_data["mailbox"].save(update_fields=["status", "outbound_enabled"])
    email = email_services.queue_outbound_ticket_reply(
        workspace=support_data["workspace"],
        ticket=support_data["ticket"],
        sender="support@example.com",
        recipients=["pat@example.com"],
        subject="Re: Open",
        text_body="We are checking this now.",
    )
    result = email_services.send_queued_email_message(email.pk)
    email.refresh_from_db()
    assert result["status"] == "sent"
    assert email.status == EmailMessage.Status.PROCESSED
    assert email.delivery_attempts.filter(status="sent").exists()
    assert len(mail.outbox) == 1
    assert str(support_data["ticket"].pk) in mail.outbox[0].subject


@pytest.mark.django_db
def test_outbound_email_failure_records_failed_attempt(monkeypatch, support_data):
    email = email_services.queue_outbound_ticket_reply(
        workspace=support_data["workspace"],
        ticket=support_data["ticket"],
        sender="support@example.com",
        recipients=["pat@example.com"],
        subject="Re: Open",
        text_body="We are checking this now.",
    )

    def fail_send(self, fail_silently=False):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", fail_send)
    result = email_services.send_queued_email_message(email.pk)
    email.refresh_from_db()
    assert result["status"] == "failed"
    assert email.status == EmailMessage.Status.FAILED
    assert email.delivery_attempts.filter(status="failed", response__contains="smtp unavailable").exists()


@pytest.mark.django_db
def test_agent_sends_customer_email_reply_from_ticket_detail(settings, client, support_data):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    support_data["mailbox"].status = MailboxChannel.Status.READY
    support_data["mailbox"].outbound_enabled = True
    support_data["mailbox"].save(update_fields=["status", "outbound_enabled"])

    client.login(username="agent", password="password")
    response = client.post(
        reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]),
        {"subject": "Re: Open", "body": "We are checking this now."},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("ticket_detail", args=[support_data["ticket"].pk])
    comment = TicketComment.objects.get(workspace=support_data["workspace"], ticket=support_data["ticket"], visibility=TicketComment.Visibility.PUBLIC)
    assert comment.author == support_data["agent"]
    assert comment.body == "We are checking this now."
    outbound = EmailMessage.objects.get(workspace=support_data["workspace"], ticket=support_data["ticket"], direction=EmailMessage.Direction.OUTBOUND)
    assert outbound.comment == comment
    assert outbound.status == EmailMessage.Status.PROCESSED
    assert outbound.sender == "support@example.com"
    assert outbound.recipients == ["pat@example.com"]
    assert str(support_data["ticket"].pk) in outbound.subject
    assert outbound.delivery_attempts.filter(status=EmailDeliveryAttempt.Status.SENT).exists()
    assert ActivityEvent.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], event_type="email.reply_sent").exists()
    assert SearchDocument.objects.filter(workspace=support_data["workspace"], entity_type=SearchDocument.EntityType.COMMENT, object_id=comment.pk, customer_visible=True).exists()
    support_data["ticket"].refresh_from_db()
    assert support_data["ticket"].status == Ticket.Status.PENDING
    assert support_data["ticket"].next_response_due_at is None
    assert len(mail.outbox) == 1
    assert mail.outbox[0].body == "We are checking this now."


@pytest.mark.django_db
def test_ticket_email_reply_requires_support_access(client, support_data):
    User = get_user_model()
    viewer = User.objects.create_user("viewer", password="password")
    WorkspaceMembership.objects.create(workspace=support_data["workspace"], user=viewer, role=WorkspaceMembership.Role.VIEWER)

    client.login(username="viewer", password="password")
    response = client.post(reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]), {"body": "Nope"})
    assert response.status_code == 403

    client.logout()
    client.login(username="customer", password="password")
    response = client.post(reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]), {"body": "Nope"})
    assert response.status_code == 403
    assert not TicketComment.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], visibility=TicketComment.Visibility.PUBLIC).exists()
    assert not EmailMessage.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], direction=EmailMessage.Direction.OUTBOUND).exists()


@pytest.mark.django_db
def test_ticket_email_reply_missing_recipient_does_not_create_records(client, support_data):
    support_data["ticket"].contact = None
    support_data["ticket"].requester = None
    support_data["ticket"].save(update_fields=["contact", "requester", "updated_at"])

    client.login(username="agent", password="password")
    response = client.post(
        reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]),
        {"subject": "Re: Open", "body": "Anyone there?"},
        follow=True,
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "No customer email address is available for this ticket." in body
    assert not TicketComment.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], visibility=TicketComment.Visibility.PUBLIC).exists()
    assert not EmailMessage.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], direction=EmailMessage.Direction.OUTBOUND).exists()


@pytest.mark.django_db
def test_ticket_email_reply_smtp_failure_keeps_comment_and_failed_email(monkeypatch, client, support_data):
    def fail_send(self, fail_silently=False):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", fail_send)
    client.login(username="agent", password="password")
    response = client.post(
        reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]),
        {"subject": "Re: Open", "body": "We tried to send this."},
        follow=True,
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "Email send failed: smtp unavailable" in body
    comment = TicketComment.objects.get(workspace=support_data["workspace"], ticket=support_data["ticket"], visibility=TicketComment.Visibility.PUBLIC)
    outbound = EmailMessage.objects.get(workspace=support_data["workspace"], ticket=support_data["ticket"], direction=EmailMessage.Direction.OUTBOUND)
    assert outbound.comment == comment
    assert outbound.status == EmailMessage.Status.FAILED
    assert outbound.delivery_attempts.filter(status=EmailDeliveryAttempt.Status.FAILED, response__contains="smtp unavailable").exists()
    assert ActivityEvent.objects.filter(workspace=support_data["workspace"], ticket=support_data["ticket"], event_type="email.reply_failed").exists()


@pytest.mark.django_db
def test_ticket_detail_renders_email_reply_panel_and_recent_outbound_status(client, support_data):
    email_message = email_services.queue_outbound_ticket_reply(
        workspace=support_data["workspace"],
        ticket=support_data["ticket"],
        sender="support@example.com",
        recipients=["pat@example.com"],
        subject="Re: Open",
        text_body="Last response.",
    )
    email_services.record_email_delivery_attempt(
        workspace=support_data["workspace"],
        email_message=email_message,
        status=EmailDeliveryAttempt.Status.FAILED,
        response="smtp unavailable",
    )

    client.login(username="agent", password="password")
    response = client.get(reverse("ticket_detail", args=[support_data["ticket"].pk]))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Email customer" in body
    assert "pat@example.com" in body
    assert "support@example.com" in body
    assert reverse("ticket_send_email_reply", args=[support_data["ticket"].pk]) in body
    assert "Recent outbound email" in body
    assert "Failed" in body
    assert "smtp unavailable" in body


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
def test_settings_application_storage_tab_shows_env_only_status(client, support_data):
    client.login(username="admin", password="password")
    response = client.get(reverse("team_settings"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Attachment storage" in body
    assert "Configured by environment" in body
    assert "Deployment storage status" in body
    assert "storage credentials are not stored in the database" in body
    assert "Save storage" not in body
    assert "secret_access_key" not in body


@pytest.mark.django_db
def test_settings_sections_render_redesigned_admin_panels(client, support_data):
    client.login(username="admin", password="password")
    sections = {
        "theme": ["Workspace theme", "GitHub Dark", "Catppuccin Mocha"],
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
def test_workspace_theme_form_validates_custom_tokens(support_data):
    from workspaces.forms import WorkspaceThemeForm

    form = WorkspaceThemeForm(
        {
            "theme_preset": "github_dark",
            "primary": "#ff00aa",
            "primary_hover": "#cc0088",
            "background": "#0d1117",
            "panel": "#161b22",
            "text": "#f0f6fc",
            "muted_text": "#8b949e",
            "border": "#30363d",
            "sidebar": "#010409",
            "sidebar_text": "#f0f6fc",
            "success": "#3fb950",
            "warning": "#d29922",
            "danger": "#f85149",
            "info": "#58a6ff",
        },
        instance=support_data["workspace"],
    )
    assert form.is_valid()
    workspace = form.save()
    assert workspace.theme_preset == "github_dark"
    assert workspace.theme_custom_tokens["primary"] == "#ff00aa"


@pytest.mark.django_db
def test_workspace_theme_form_rejects_invalid_hex_and_can_reset(support_data):
    from workspaces.forms import WorkspaceThemeForm

    invalid = WorkspaceThemeForm({"theme_preset": "catppuccin_mocha", "primary": "not-a-color"}, instance=support_data["workspace"])
    assert not invalid.is_valid()
    assert "primary" in invalid.errors

    workspace = support_data["workspace"]
    workspace.theme_preset = "dracula"
    workspace.theme_custom_tokens = {"primary": "#ff00aa"}
    workspace.save(update_fields=["theme_preset", "theme_custom_tokens"])
    reset = WorkspaceThemeForm({"theme_preset": "nord", "reset_custom_tokens": "on"}, instance=workspace)
    assert reset.is_valid()
    workspace = reset.save()
    assert workspace.theme_preset == "nord"
    assert workspace.theme_custom_tokens == {}


@pytest.mark.django_db
def test_admin_can_update_workspace_theme_settings(client, support_data):
    client.login(username="admin", password="password")
    response = client.post(
        reverse("team_settings"),
        {
            "action": "theme",
            "theme_preset": "catppuccin_mocha",
            "primary": "#f5c2e7",
            "primary_hover": "#cba6f7",
            "background": "#1e1e2e",
            "panel": "#202033",
            "text": "#cdd6f4",
            "muted_text": "#a6adc8",
            "border": "#45475a",
            "sidebar": "#11111b",
            "sidebar_text": "#cdd6f4",
            "success": "#a6e3a1",
            "warning": "#f9e2af",
            "danger": "#f38ba8",
            "info": "#89b4fa",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("?section=theme")
    support_data["workspace"].refresh_from_db()
    assert support_data["workspace"].theme_preset == "catppuccin_mocha"
    assert support_data["workspace"].theme_custom_tokens["panel"] == "#202033"


@pytest.mark.django_db
def test_workspace_theme_css_renders_for_internal_and_portal_pages(client, support_data):
    workspace = support_data["workspace"]
    workspace.theme_preset = "github_dark"
    workspace.theme_custom_tokens = {"primary": "#ff00aa"}
    workspace.save(update_fields=["theme_preset", "theme_custom_tokens"])

    client.login(username="agent", password="password")
    body = client.get(reverse("dashboard")).content.decode()
    assert 'data-theme-preset="github_dark"' in body
    assert "--tl-accent: #ff00aa;" in body
    assert "--tl-panel: #161b22;" in body

    client.logout()
    client.login(username="customer", password="password")
    portal_body = client.get(reverse("portal_ticket_list")).content.decode()
    assert 'data-theme-preset="github_dark"' in portal_body
    assert "--tl-accent: #ff00aa;" in portal_body


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
