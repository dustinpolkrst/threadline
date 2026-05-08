import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
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
    return {"agent": agent, "customer": customer, "ticket": ticket, "other_ticket": other_ticket}


@pytest.mark.django_db
def test_customer_portal_hides_internal_notes_and_private_time(client, demo):
    client.login(username="customer", password="password")
    response = client.get(reverse("portal_ticket_detail", args=[demo["ticket"].pk]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "public" in content
    assert "internal secret" not in content
    assert "visible time 30m" in content
    assert "60" not in content


@pytest.mark.django_db
def test_customer_cannot_access_other_workspace_ticket(client, demo):
    client.login(username="customer", password="password")
    response = client.get(reverse("portal_ticket_detail", args=[demo["other_ticket"].pk]))
    assert response.status_code == 404


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
