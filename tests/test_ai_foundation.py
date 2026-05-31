import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from ai.client import OpenRouterError, build_request_payload, parse_analysis_response
from ai.context import build_analysis_messages, build_ticket_context
from ai.models import AIRun, AISuggestedAction, AIProviderSettings, CRMInsight, QueueIntelligenceSnapshot, SolutionSnippet, TicketAIAnalysis, TicketReplyDraft, TimeEntrySuggestion, WorkspaceDigest
from ai.services import approve_reply_draft, approve_solution_snippet, apply_analysis, apply_selected_ticket_suggestions, build_queue_intelligence, generate_crm_insight, generate_reply_draft, generate_workspace_digest, run_ticket_analysis, suggest_time_entry, time_cleanup_context
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from search.models import SearchDocument
from tickets.models import Ticket, TicketComment
from workspaces.models import Workspace, WorkspaceMembership
from ai import services as ai_services


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
def test_ai_usage_summary_counts_current_month_only(ai_data):
    now = timezone.now()
    old = now - timezone.timedelta(days=45)
    old_run = AIRun.objects.create(workspace=ai_data["workspace"], workflow=AIRun.Workflow.REPLY_COMPOSER, status=AIRun.Status.SUCCEEDED, total_tokens=30, completed_at=old)
    AIRun.objects.filter(pk=old_run.pk).update(created_at=old)
    AIRun.objects.create(workspace=ai_data["workspace"], workflow=AIRun.Workflow.REPLY_COMPOSER, status=AIRun.Status.SUCCEEDED, total_tokens=12)
    AIRun.objects.create(workspace=ai_data["other_workspace"], workflow=AIRun.Workflow.REPLY_COMPOSER, status=AIRun.Status.SUCCEEDED, total_tokens=99)
    summary = ai_services.ai_usage_summary(ai_data["workspace"], today=now.date())
    assert summary["run_count"] == 1
    assert summary["total_tokens"] == 12
    assert summary["monthly_token_cap"] == 0
    assert summary["monthly_run_cap"] == 0


@pytest.mark.django_db
def test_ai_budget_blocks_ticket_analysis_before_provider_call(monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test", monthly_token_cap=10)
    AIRun.objects.create(workspace=ai_data["workspace"], workflow=AIRun.Workflow.REPLY_COMPOSER, status=AIRun.Status.SUCCEEDED, total_tokens=10)
    analysis = TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider should not be called after cap is reached")

    monkeypatch.setattr("ai.services.send_chat_completion", fail_if_called)
    ai_services.run_ticket_analysis(analysis)
    analysis.refresh_from_db()
    assert analysis.status == TicketAIAnalysis.Status.FAILED
    assert analysis.error_code == "budget_exceeded"


@pytest.mark.django_db
def test_prune_ai_generation_retention_clears_old_outputs(ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], generation_retention_days=7)
    old_run = AIRun.objects.create(
        workspace=ai_data["workspace"],
        workflow=AIRun.Workflow.REPLY_COMPOSER,
        status=AIRun.Status.SUCCEEDED,
        output={"body": "old generated text"},
        context_refs=[{"ticket": "old"}],
        selected_actions=["reply"],
        rejected_actions=["note"],
        completed_at=timezone.now() - timezone.timedelta(days=30),
    )
    fresh_run = AIRun.objects.create(
        workspace=ai_data["workspace"],
        workflow=AIRun.Workflow.REPLY_COMPOSER,
        status=AIRun.Status.SUCCEEDED,
        output={"body": "fresh generated text"},
        context_refs=[{"ticket": "fresh"}],
        completed_at=timezone.now(),
    )
    pruned = ai_services.prune_ai_generation_retention()
    old_run.refresh_from_db()
    fresh_run.refresh_from_db()
    assert pruned == 1
    assert old_run.output == {}
    assert old_run.context_refs == []
    assert old_run.selected_actions == []
    assert old_run.rejected_actions == []
    assert fresh_run.output == {"body": "fresh generated text"}


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
    assert settings.api_key == ""
    assert settings.encrypted_api_key
    assert settings.get_api_key() == "existing-key"
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
    monkeypatch.setattr("ai.services.send_chat_completion", lambda ai_settings, messages, max_tokens=2400: response)
    original_priority = ai_data["ticket"].priority
    run_ticket_analysis(analysis)
    analysis.refresh_from_db()
    ai_data["ticket"].refresh_from_db()
    assert analysis.status == TicketAIAnalysis.Status.SUCCEEDED
    assert analysis.summary == "Likely SSO configuration issue."
    assert analysis.customer_reply_draft.startswith("We are checking")
    assert analysis.root_cause_notes == "SSO mapping appears stale."
    assert analysis.total_tokens == 30
    assert ai_data["ticket"].priority == original_priority
    assert settings.enabled is True
    assert AIRun.objects.filter(workspace=ai_data["workspace"], workflow=AIRun.Workflow.TICKET_WORKBENCH, subject_id=ai_data["ticket"].pk).exists()
    assert TicketReplyDraft.objects.filter(workspace=ai_data["workspace"], ticket=ai_data["ticket"], audience=TicketReplyDraft.Audience.CUSTOMER).exists()
    assert AISuggestedAction.objects.filter(workspace=ai_data["workspace"], ticket_analysis=analysis, action_type="customer_reply").exists()


@pytest.mark.django_db
def test_analysis_parser_accepts_fenced_json(ai_data):
    response = {
        "model": "openrouter/mock",
        "choices": [{"message": {"content": f"```json\n{json.dumps(_analysis_payload())}\n```"}}],
        "usage": {},
    }
    parsed, usage = parse_analysis_response(response)
    assert parsed["summary"] == "Likely SSO configuration issue."
    assert usage["raw_model"] == "openrouter/mock"


@pytest.mark.django_db
def test_malformed_analysis_response_marks_failed_with_preview(monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    analysis = TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"])
    monkeypatch.setattr(
        "ai.services.send_chat_completion",
        lambda ai_settings, messages, max_tokens=2400: {"model": "openrouter/mock", "choices": [{"message": {"content": "I think this is a staging flag issue."}}]},
    )
    run_ticket_analysis(analysis)
    analysis.refresh_from_db()
    assert analysis.status == TicketAIAnalysis.Status.FAILED
    assert analysis.error_code == "malformed_json"
    assert "Preview:" in analysis.error_message
    assert analysis.completed_at is not None


def test_parser_reads_provider_structured_fields():
    parsed, _ = parse_analysis_response({"model": "m", "choices": [{"message": {"parsed": _analysis_payload()}}]})
    assert parsed["triage"]["priority"] == "high"


def test_parser_raises_with_safe_preview_for_non_json():
    with pytest.raises(OpenRouterError) as exc:
        parse_analysis_response({"choices": [{"message": {"content": "not json at all"}}]})
    assert exc.value.code == "malformed_json"
    assert "Preview: not json at all" in str(exc.value)


def test_parser_rejects_missing_required_fields():
    with pytest.raises(OpenRouterError) as exc:
        parse_analysis_response({"choices": [{"message": {"content": json.dumps({"summary": "too small"})}}]})
    assert exc.value.code == "malformed_json"
    assert "missing or invalid fields" in str(exc.value)


def test_parser_reports_truncated_output():
    with pytest.raises(OpenRouterError) as exc:
        parse_analysis_response({"choices": [{"finish_reason": "length", "message": {"content": '{"summary":"cut off'}}]})
    assert exc.value.code == "truncated_output"
    assert "truncated before valid JSON completed" in str(exc.value)


@pytest.mark.django_db
def test_truncated_analysis_response_marks_failed(monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    analysis = TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"])
    monkeypatch.setattr(
        "ai.services.send_chat_completion",
        lambda ai_settings, messages, max_tokens=2400: {"model": "openrouter/mock", "choices": [{"finish_reason": "length", "message": {"content": '{"summary":"cut off'}}]},
    )
    run_ticket_analysis(analysis)
    analysis.refresh_from_db()
    assert analysis.status == TicketAIAnalysis.Status.FAILED
    assert analysis.error_code == "truncated_output"
    assert analysis.completed_at is not None


@pytest.mark.django_db
def test_analysis_context_is_compact_json_and_bounded(ai_data):
    settings = AIProviderSettings.objects.create(workspace=ai_data["workspace"], max_historical_tickets=5)
    for index in range(20):
        TicketComment.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], body=f"comment {index}")
    messages = build_analysis_messages(ai_data["ticket"], settings)
    body = messages[1]["content"]
    assert "Context JSON:" in body
    assert "'current_ticket'" not in body
    context_json = body.split("Context JSON:\n", 1)[1]
    parsed = json.loads(context_json)
    assert len(parsed["comments"]) == 12
    assert "secret123" not in context_json
    assert "[REDACTED]" in context_json


@pytest.mark.django_db
def test_run_ticket_analysis_uses_configured_token_budget(monkeypatch, settings, ai_data):
    settings.OPENROUTER_ANALYSIS_MAX_TOKENS = 3456
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    analysis = TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"])
    seen = {}

    def fake_send(ai_settings, messages, max_tokens):
        seen["max_tokens"] = max_tokens
        return {
            "model": "openrouter/mock",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_analysis_payload())}}],
            "usage": {},
        }

    monkeypatch.setattr("ai.services.send_chat_completion", fake_send)
    run_ticket_analysis(analysis)
    assert seen["max_tokens"] == 3456


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
    assert SearchDocument.objects.filter(workspace=ai_data["workspace"], object_id=ai_data["ticket"].pk, body__contains="sso").exists()


@pytest.mark.django_db
def test_apply_selected_ticket_suggestions_are_human_approved(ai_data):
    analysis = TicketAIAnalysis.objects.create(
        workspace=ai_data["workspace"],
        ticket=ai_data["ticket"],
        requested_by=ai_data["agent"],
        status=TicketAIAnalysis.Status.SUCCEEDED,
        suggested_priority=Ticket.Priority.URGENT,
        suggested_status=Ticket.Status.PENDING,
        suggested_tags=["cache"],
        customer_reply_draft="Customer-safe update draft.",
        internal_note_draft="Internal note draft.",
    )
    TicketReplyDraft.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], analysis=analysis, audience=TicketReplyDraft.Audience.CUSTOMER, body=analysis.customer_reply_draft)
    applied = apply_selected_ticket_suggestions(analysis, ai_data["agent"], ["priority", "tags", "internal_note", "customer_reply"])
    ai_data["ticket"].refresh_from_db()
    assert set(applied) == {"priority", "tags", "internal_note", "customer_reply"}
    assert ai_data["ticket"].priority == Ticket.Priority.URGENT
    assert "cache" in ai_data["ticket"].tags
    assert TicketComment.objects.filter(ticket=ai_data["ticket"], body="Internal note draft.").exists()
    assert TicketReplyDraft.objects.get(analysis=analysis, audience=TicketReplyDraft.Audience.CUSTOMER).status == TicketReplyDraft.Status.APPROVED


@pytest.mark.django_db
def test_crm_time_and_digest_ai_artifacts_are_workspace_scoped(ai_data):
    insight = generate_crm_insight(ai_data["org"], ai_data["agent"])
    suggestion = suggest_time_entry(ai_data["ticket"], ai_data["agent"])
    digest = generate_workspace_digest(ai_data["workspace"], ai_data["admin"])
    assert CRMInsight.objects.filter(workspace=ai_data["workspace"], pk=insight.pk, organization=ai_data["org"]).exists()
    assert TimeEntrySuggestion.objects.filter(workspace=ai_data["workspace"], pk=suggestion.pk, ticket=ai_data["ticket"]).exists()
    assert WorkspaceDigest.objects.filter(workspace=ai_data["workspace"], pk=digest.pk).exists()
    assert not CRMInsight.objects.filter(workspace=ai_data["other_workspace"], pk=insight.pk).exists()


@pytest.mark.django_db
def test_reply_composer_creates_draft_and_approval_posts_public_comment(monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")

    def fake_send(ai_settings, messages, max_tokens=1200, structured=True, response_format=None):
        assert response_format["json_schema"]["name"] == "threadline_reply_draft"
        return {
            "id": "gen-reply-1",
            "model": "openrouter/mock",
            "choices": [{"message": {"content": json.dumps({"body": "Thanks, we are checking this now.", "reason": "Clear customer-safe update."})}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
        }

    monkeypatch.setattr("ai.services.send_chat_completion", fake_send)
    draft = generate_reply_draft(ai_data["ticket"], ai_data["agent"], intent="customer_safe", source_text="internal rough note")
    assert draft.status == TicketReplyDraft.Status.DRAFT
    assert draft.run.provider_generation_id == "gen-reply-1"
    approve_reply_draft(draft, ai_data["agent"])
    draft.refresh_from_db()
    assert draft.status == TicketReplyDraft.Status.APPROVED
    assert TicketComment.objects.filter(workspace=ai_data["workspace"], ticket=ai_data["ticket"], visibility=TicketComment.Visibility.PUBLIC, body=draft.body).exists()


@pytest.mark.django_db
def test_solution_memory_approval_indexes_internal_snippet(ai_data):
    snippet = SolutionSnippet.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], title="SSO cache reset", body="Reset stale SSO mapping cache.", tags=["sso"])
    approve_solution_snippet(snippet, ai_data["agent"])
    snippet.refresh_from_db()
    assert snippet.approved is True
    assert SearchDocument.objects.filter(workspace=ai_data["workspace"], entity_type=SearchDocument.EntityType.SOLUTION_SNIPPET, object_id=snippet.pk, customer_visible=False, body__contains="SSO").exists()


@pytest.mark.django_db
def test_openrouter_backed_crm_insight_uses_structured_output(monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")

    def fake_send(ai_settings, messages, max_tokens=1800, structured=True, response_format=None):
        assert response_format["json_schema"]["name"] == "threadline_crm_insight"
        return {
            "model": "openrouter/mock",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Acme has recurring SSO issues.",
                                "support_tone": "calm but blocked",
                                "recommended_next_touch": "Confirm affected users before next reply.",
                                "recurring_issues": ["SSO"],
                                "product_areas": ["Authentication"],
                                "risks": ["Repeated login failures"],
                                "suggestions": ["Review identity provider settings"],
                                "hygiene_suggestions": ["Add renewal date"],
                            }
                        )
                    }
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr("ai.services.send_chat_completion", fake_send)
    insight = generate_crm_insight(ai_data["org"], ai_data["agent"])
    assert insight.summary == "Acme has recurring SSO issues."
    assert insight.support_tone == "calm but blocked"
    assert insight.hygiene_suggestions == ["Add renewal date"]


@pytest.mark.django_db
def test_queue_intelligence_and_time_cleanup_are_workspace_scoped(ai_data):
    Ticket.objects.create(workspace=ai_data["workspace"], organization=None, title="urgent missing customer", description="urgent", priority=Ticket.Priority.NORMAL)
    snapshot = build_queue_intelligence(ai_data["workspace"], ai_data["agent"])
    cleanup = time_cleanup_context(ai_data["workspace"], ai_data["agent"])
    assert QueueIntelligenceSnapshot.objects.filter(workspace=ai_data["workspace"], pk=snapshot.pk).exists()
    assert snapshot.likely_urgent
    assert ai_data["other_ticket"].title not in json.dumps(snapshot.likely_urgent + snapshot.missing_customer_info)
    assert ai_data["ticket"] in list(cleanup["unlogged_tickets"])


@pytest.mark.django_db
def test_ai_enqueue_failure_does_not_run_synchronously(client, monkeypatch, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")

    def fail_delay(*args, **kwargs):
        raise RuntimeError("broker unavailable")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_ticket_analysis should not run in the web request")

    monkeypatch.setattr("ai.views.analyze_ticket_with_ai.delay", fail_delay)
    monkeypatch.setattr("ai.views.run_ticket_analysis", fail_if_called, raising=False)
    client.login(username="ai-agent", password="password")
    response = client.post(reverse("ticket_ai_analyze", args=[ai_data["ticket"].pk]))
    assert response.status_code == 302
    analysis = TicketAIAnalysis.objects.get(ticket=ai_data["ticket"])
    assert analysis.status == TicketAIAnalysis.Status.FAILED
    assert analysis.error_code == "queue_unavailable"


@pytest.mark.django_db
def test_ai_panel_polls_for_running_analysis_and_blocks_customers(client, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    TicketAIAnalysis.objects.create(workspace=ai_data["workspace"], ticket=ai_data["ticket"], requested_by=ai_data["agent"], status=TicketAIAnalysis.Status.RUNNING)
    client.login(username="ai-customer", password="password")
    assert client.get(reverse("ticket_ai_panel", args=[ai_data["ticket"].pk])).status_code == 403
    client.logout()
    client.login(username="ai-agent", password="password")
    response = client.get(reverse("ticket_ai_panel", args=[ai_data["ticket"].pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert 'hx-trigger="every 3s"' in body
    assert "Running" in body


@pytest.mark.django_db
def test_ai_panel_terminal_states_do_not_poll(client, ai_data):
    AIProviderSettings.objects.create(workspace=ai_data["workspace"], enabled=True, api_key="sk-or-test")
    TicketAIAnalysis.objects.create(
        workspace=ai_data["workspace"],
        ticket=ai_data["ticket"],
        requested_by=ai_data["agent"],
        status=TicketAIAnalysis.Status.SUCCEEDED,
        summary="Solved by refreshing flag cache.",
        solution_draft="Ask engineering to refresh the flag cache.",
    )
    client.login(username="ai-agent", password="password")
    body = client.get(reverse("ticket_ai_panel", args=[ai_data["ticket"].pk])).content.decode()
    assert 'hx-trigger="every 3s"' not in body
    assert "Solved by refreshing flag cache." in body
    assert "Ask engineering to refresh the flag cache." in body


def _analysis_payload():
    return {
        "summary": "Likely SSO configuration issue.",
        "root_cause_notes": "SSO mapping appears stale.",
        "customer_reply_draft": "We are checking the SSO mapping and will follow up shortly.",
        "internal_note_draft": "Check SSO mapping and user session state.",
        "missing_info": ["Affected user email"],
        "escalation_risk": "medium",
        "next_actions": ["Verify SSO mapping", "Ask customer for affected user"],
        "triage": {
            "priority": "high",
            "status": "open",
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
