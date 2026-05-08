import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from ai.client import build_request_payload, parse_analysis_response
from ai.context import build_ticket_context
from ai.models import AIProviderSettings, TicketAIAnalysis
from ai.services import apply_analysis, run_ticket_analysis
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
from workspaces.models import Workspace, WorkspaceMembership


@pytest.fixture
def ai_data(db):
    User = get_user_model()
    workspace = Workspace.objects.create(name="AI Demo", slug="ai-demo")
    other_workspace = Workspace.objects.create(name="Other AI", slug="other-ai")
    admin = User.objects.create_user("ai-admin", password="password")
    agent = User.objects.create_user("ai-agent", password="password")
    customer = User.objects.create_user("ai-customer", password="password")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceMembership.Role.ADMIN)
    WorkspaceMembership.objects.create(workspace=workspace, user=agent, role=WorkspaceMembership.Role.AGENT)
    org = Organization.objects.create(workspace=workspace, name="Acme AI", domain="acme.example")
    other_org = Organization.objects.create(workspace=other_workspace, name="Other Org")
    contact = Contact.objects.create(workspace=workspace, organization=org, name="Pat", email="pat-ai@example.com")
    CustomerProfile.objects.create(user=customer, workspace=workspace, organization=org, contact=contact)
    ticket = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Cannot log in", description="password=secret123")
    TicketComment.objects.create(workspace=workspace, ticket=ticket, author=agent, body="API_KEY=abc123 internal clue")
    historical = Ticket.objects.create(workspace=workspace, organization=org, contact=contact, title="Login reset", description="Reset SSO mapping")
    other_ticket = Ticket.objects.create(workspace=other_workspace, organization=other_org, title="Other tenant secret")
    return {
        "workspace": workspace,
        "other_workspace": other_workspace,
        "admin": admin,
        "agent": agent,
        "customer": customer,
        "org": org,
        "ticket": ticket,
        "historical": historical,
        "other_ticket": other_ticket,
    }


@pytest.mark.django_db
def test_openrouter_request_enforces_zdr_and_schema(ai_data):
    settings = AIProviderSettings.objects.create(workspace=ai_data["workspace"], api_key="sk-or-test", model="openrouter/auto")
    payload = build_request_payload(settings, [{"role": "user", "content": "Analyze"}])
    assert payload["provider"]["zdr"] is True
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["metadata"]["workspace_id"] == str(ai_data["workspace"].pk)


@pytest.mark.django_db
def test_ai_settings_preserves_api_key_and_blocks_customer(client, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], api_key="existing-key")
    client.login(username="ai-customer", password="password")
    assert client.get(reverse("team_settings") + "?section=ai").status_code == 403
    client.logout()
    client.login(username="ai-admin", password="password")
    body = client.get(reverse("team_settings") + "?section=ai").content.decode()
    assert "OpenRouter configuration" in body
    response = client.post(
        reverse("team_settings"),
        {
            "action": "ai",
            "enabled": "on",
            "api_key": "",
            "model": "openrouter/auto",
            "zdr_only": "on",
            "max_historical_tickets": "4",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("?section=ai")
    settings = AIProviderSettings.objects.get(workspace=ai_data["workspace"])
    assert settings.api_key == "existing-key"
    assert settings.enabled is True
    assert settings.zdr_only is True


@pytest.mark.django_db
def test_ticket_context_is_workspace_and_client_scoped(ai_data):
    settings = AIProviderSettings.objects.create(workspace=ai_data["workspace"], max_historical_tickets=5)
    context = build_ticket_context(ai_data["ticket"], settings)
    assert "Login reset" in json.dumps(context)
    assert "Other tenant secret" not in json.dumps(context)
    assert "secret123" not in json.dumps(context)
    assert "[REDACTED]" in json.dumps(context)


@pytest.mark.django_db
def test_draft_generation_creates_analysis_without_mutating_ticket(monkeypatch, ai_data):
    settings = AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    analysis = TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"])
    response = {
        "model": "openrouter/mock",
        "choices": [{"message": {"content": json.dumps(_analysis_payload())}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    monkeypatch.setattr("ai.services.send_chat_completion", lambda ai_settings, messages: response)
    original_priority = ai_data["ticket"].priority
    run_ticket_analysis(analysis)
    analysis.refresh_from_db()
    ai_data["ticket"].refresh_from_db()
    assert analysis.status == TicketAIAnalysis.Status.SUCCEEDED
    assert analysis.summary == "Likely SSO configuration issue."
    assert analysis.total_tokens == 30
    assert ai_data["ticket"].priority == original_priority
    assert settings.enabled is True


@pytest.mark.django_db
def test_auto_triage_requires_setting_and_apply_updates_ticket(ai_data):
    settings = AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    analysis = TicketAIAnalysis.objects.create(
        workspace=ai_data["workspace"],
        ticket=ai_data["ticket"],
        requested_by=ai_data["agent"],
        status=TicketAIAnalysis.Status.SUCCEEDED,
        suggested_priority=Ticket.Priority.HIGH,
        suggested_tags=["sso", "login"],
        solution_draft="Check SSO mapping.",
        summary="SSO issue",
    )
    with pytest.raises(ValueError):
        apply_analysis(analysis, ai_data["agent"])
    settings.auto_triage_enabled = True
    settings.save(update_fields=["auto_triage_enabled"])
    apply_analysis(analysis, ai_data["agent"])
    ai_data["ticket"].refresh_from_db()
    analysis.refresh_from_db()
    assert ai_data["ticket"].priority == Ticket.Priority.HIGH
    assert "sso" in ai_data["ticket"].tags
    assert analysis.status == TicketAIAnalysis.Status.APPLIED
    assert TicketComment.objects.filter(ticket=ai_data["ticket"], body__contains="AI triage applied").exists()


def _analysis_payload():
    return {
        "summary": "Likely SSO configuration issue.",
        "triage": {
            "priority": "high",
            "tags": ["sso", "login"],
            "confidence": 0.82,
            "reasoning": "Historical login reset ticket is similar.",
            "assignee_reason": "Assign to identity specialist.",
        },
        "client_context": ["Prior SSO mapping reset solved a similar issue."],
        "solution_draft": "Verify SSO mapping and reset the user session.",
        "risks": ["Need customer confirmation."],
        "context_refs": [{"type": "ticket", "id": "1", "title": "Login reset"}],
    }
