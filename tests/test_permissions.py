import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketAttachment, TicketComment
from time_tracking.models import ActiveTimer, TimeEntry
from workspaces.models import Workspace, WorkspaceMembership


@pytest.fixture
def demo(db):
    User = get_user_model()
    workspace = Workspace.objects.create(name="Demo", slug="demo")
    other_workspace = Workspace.objects.create(name="Other", slug="other")
    agent = User.objects.create_user("agent", password="password")
    WorkspaceMembership.objects.create(workspace=workspace, user=agent, role=WorkspaceMembership.Role.AGENT)
    org = Organization.objects.create(workspace=workspace, name="Acme")
    contact = Contact.objects.create(workspace=workspace, organization=org, name="Pat", email="pat@example.com")
    customer = User.objects.create_user("customer", password="password")
    CustomerProfile.objects.create(user=customer, workspace=workspace, organization=org, contact=contact)
    other_org = Organization.objects.create(workspace=other_workspace, name="OtherCo")
    other_contact = Contact.objects.create(workspace=other_workspace, organization=other_org, name="Other", email="other@example.com")
    ticket = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Visible", description="Portal ticket")
    other_ticket = Ticket.objects.create(workspace=other_workspace, organization=other_org, contact=other_contact, title="Hidden", description="Other tenant")
    TicketComment.objects.create(workspace=workspace, ticket=ticket, author=agent, body="public", visibility=TicketComment.Visibility.PUBLIC)
    TicketComment.objects.create(workspace=workspace, ticket=ticket, author=agent, body="internal secret", visibility=TicketComment.Visibility.INTERNAL)
    TimeEntry.objects.create(workspace=workspace, user=agent, ticket=ticket, organization=org, contact=contact, started_at=timezone.now(), duration_minutes=30, customer_visible=True)
    TimeEntry.objects.create(workspace=workspace, user=agent, ticket=ticket, organization=org, contact=contact, started_at=timezone.now(), duration_minutes=60, customer_visible=False)
    return {"agent": agent, "customer": customer, "ticket": ticket, "other_ticket": other_ticket, "workspace": workspace, "other_workspace": other_workspace}


@pytest.mark.django_db
def test_customer_portal_hides_internal_notes_and_private_time(client, demo):
    client.login(username="customer", password="password")
    response = client.get(reverse("portal_ticket_detail", args=[demo["ticket"].pk]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "public" in content
    assert "internal secret" not in content
    assert "visible time 30m" in content
    assert "60m" not in content


@pytest.mark.django_db
def test_customer_cannot_access_other_workspace_ticket(client, demo):
    client.login(username="customer", password="password")
    response = client.get(reverse("portal_ticket_detail", args=[demo["other_ticket"].pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_customer_portal_is_contact_scoped(client, demo):
    other_contact = Contact.objects.create(
        workspace=demo["workspace"],
        organization=demo["ticket"].organization,
        name="Other Contact",
        email="other-contact@example.com",
    )
    other_ticket = Ticket.objects.create(
        workspace=demo["workspace"],
        organization=demo["ticket"].organization,
        contact=other_contact,
        title="Same org private ticket",
        description="Different contact",
    )
    attachment = TicketAttachment.objects.create(
        workspace=demo["workspace"],
        ticket=other_ticket,
        file=SimpleUploadedFile("other.txt", b"other"),
        display_name="other.txt",
        customer_visible=True,
    )

    client.login(username="customer", password="password")
    list_body = client.get(reverse("portal_ticket_list")).content.decode()
    assert "Visible" in list_body
    assert "Same org private ticket" not in list_body
    assert client.get(reverse("portal_ticket_detail", args=[other_ticket.pk])).status_code == 404
    assert client.post(reverse("portal_ticket_reply", args=[other_ticket.pk]), {"body": "not mine"}).status_code == 404
    assert client.get(reverse("portal_download_attachment", args=[other_ticket.pk, attachment.pk])).status_code == 404


@pytest.mark.django_db
def test_customer_cannot_access_internal_settings_or_ticket_detail(client, demo):
    client.login(username="customer", password="password")
    response = client.get(reverse("ticket_detail", args=[demo["ticket"].pk]))
    assert response.status_code == 403


@pytest.mark.django_db
def test_agent_can_start_and_stop_billable_timer(client, demo):
    client.login(username="agent", password="password")
    start_response = client.post(reverse("ticket_start_timer", args=[demo["ticket"].pk]), {"billable": "on", "notes": "Investigating"})
    assert start_response.status_code == 302
    timer = ActiveTimer.objects.get(user=demo["agent"], ticket=demo["ticket"])
    timer.started_at = timezone.now() - timezone.timedelta(minutes=7)
    timer.save(update_fields=["started_at"])

    stop_response = client.post(reverse("ticket_stop_timer", args=[demo["ticket"].pk]), {"notes": "Resolved with config change"})
    assert stop_response.status_code == 302
    assert not ActiveTimer.objects.filter(user=demo["agent"]).exists()
    entry = TimeEntry.objects.filter(user=demo["agent"], ticket=demo["ticket"], notes="Resolved with config change").latest("created_at")
    assert entry.billable is True
    assert entry.duration_minutes >= 7


@pytest.mark.django_db
def test_agent_can_log_manual_ticket_time(client, demo):
    client.login(username="agent", password="password")
    response = client.post(
        reverse("ticket_add_time", args=[demo["ticket"].pk]),
        {
            "started_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "duration_minutes": "25",
            "billable": "on",
            "notes": "Manual investigation",
        },
    )
    assert response.status_code == 302
    entry = TimeEntry.objects.get(ticket=demo["ticket"], notes="Manual investigation")
    assert entry.workspace == demo["workspace"]
    assert entry.organization == demo["ticket"].organization
    assert entry.contact == demo["ticket"].contact
    assert entry.user == demo["agent"]
    assert entry.customer_visible is False


@pytest.mark.django_db
def test_agent_can_edit_ticket_time_entry(client, demo):
    entry = TimeEntry.objects.filter(workspace=demo["workspace"], ticket=demo["ticket"]).first()
    client.login(username="agent", password="password")
    response = client.post(
        reverse("time_entry_edit", args=[entry.pk]),
        {
            "started_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "duration_minutes": "45",
            "billable": "on",
            "notes": "Adjusted after review",
        },
    )
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.duration_minutes == 45
    assert entry.notes == "Adjusted after review"
    assert entry.customer_visible is False


@pytest.mark.django_db
def test_agent_cannot_edit_other_workspace_time_entry(client, demo):
    other_entry = TimeEntry.objects.create(
        workspace=demo["other_workspace"],
        user=demo["agent"],
        ticket=demo["other_ticket"],
        started_at=timezone.now(),
        duration_minutes=10,
    )
    client.login(username="agent", password="password")
    response = client.get(reverse("time_entry_edit", args=[other_entry.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_ticket_detail_shows_all_time_entries_for_ticket(client, demo):
    old_entry = TimeEntry.objects.create(
        workspace=demo["workspace"],
        user=demo["agent"],
        ticket=demo["ticket"],
        started_at=timezone.now() - timezone.timedelta(days=45),
        duration_minutes=99,
        notes="Old month entry",
    )
    client.login(username="agent", password="password")
    response = client.get(reverse("ticket_detail", args=[demo["ticket"].pk]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Old month entry" in content
    assert f'href="/time/{old_entry.pk}/edit/"' in content


@pytest.mark.django_db
def test_ticket_mutations_require_post(client, demo):
    client.login(username="agent", password="password")
    assert client.get(reverse("ticket_resolve", args=[demo["ticket"].pk])).status_code == 405
    assert client.get(reverse("ticket_add_time", args=[demo["ticket"].pk])).status_code == 405
    assert client.get(reverse("ticket_start_timer", args=[demo["ticket"].pk])).status_code == 405


@pytest.mark.django_db
def test_viewer_is_read_only(client, demo):
    User = get_user_model()
    viewer = User.objects.create_user("viewer", password="password")
    WorkspaceMembership.objects.create(workspace=demo["workspace"], user=viewer, role=WorkspaceMembership.Role.VIEWER)

    client.login(username="viewer", password="password")
    assert client.get(reverse("ticket_detail", args=[demo["ticket"].pk])).status_code == 200
    assert client.post(reverse("ticket_resolve", args=[demo["ticket"].pk])).status_code == 403
    assert client.post(reverse("ticket_start_timer", args=[demo["ticket"].pk]), {"billable": "on"}).status_code == 403
    assert client.get(reverse("crm_import_upload")).status_code == 403
    assert client.post(reverse("ticket_ai_time_suggestion", args=[demo["ticket"].pk])).status_code == 403
