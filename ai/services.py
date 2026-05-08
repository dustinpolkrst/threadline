from django.utils import timezone

from activity.services import record_event
from tickets.models import TicketComment

from .client import OpenRouterError, parse_analysis_response, send_chat_completion
from .context import build_analysis_messages
from .models import AIProviderSettings, TicketAIAnalysis


def get_ai_settings(workspace):
    settings, _ = AIProviderSettings.objects.get_or_create(workspace=workspace)
    return settings


def run_ticket_analysis(analysis):
    analysis.status = TicketAIAnalysis.Status.RUNNING
    analysis.error_code = ""
    analysis.error_message = ""
    analysis.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    ai_settings = get_ai_settings(analysis.workspace)
    if not ai_settings.enabled:
        return _fail_analysis(analysis, "disabled", "AI is not enabled for this workspace.")
    try:
        messages = build_analysis_messages(analysis.ticket, ai_settings)
        response = send_chat_completion(ai_settings, messages)
        parsed, usage = parse_analysis_response(response)
    except OpenRouterError as exc:
        return _fail_analysis(analysis, exc.code, str(exc))

    triage = parsed.get("triage") or {}
    analysis.summary = parsed.get("summary", "")
    analysis.suggested_priority = triage.get("priority", "")
    analysis.suggested_tags = triage.get("tags") or []
    analysis.suggested_assignee_reason = triage.get("assignee_reason", "")
    analysis.solution_draft = parsed.get("solution_draft", "")
    analysis.confidence = triage.get("confidence")
    analysis.context_refs = parsed.get("context_refs") or []
    analysis.risks = parsed.get("risks") or []
    analysis.raw_model = usage["raw_model"]
    analysis.prompt_tokens = usage["prompt_tokens"]
    analysis.completion_tokens = usage["completion_tokens"]
    analysis.total_tokens = usage["total_tokens"]
    analysis.status = TicketAIAnalysis.Status.SUCCEEDED
    analysis.completed_at = timezone.now()
    analysis.save()
    return analysis


def create_queued_analysis(ticket, user, mode=TicketAIAnalysis.Mode.DRAFT):
    return TicketAIAnalysis.objects.create(
        workspace=ticket.workspace,
        ticket=ticket,
        requested_by=user,
        mode=mode,
        status=TicketAIAnalysis.Status.QUEUED,
    )


def apply_analysis(analysis, user):
    ai_settings = get_ai_settings(analysis.workspace)
    if not ai_settings.auto_triage_enabled:
        raise ValueError("Auto-triage is not enabled for this workspace.")
    if analysis.status not in [TicketAIAnalysis.Status.SUCCEEDED, TicketAIAnalysis.Status.APPLIED]:
        raise ValueError("Only successful AI analyses can be applied.")
    ticket = analysis.ticket
    update_fields = []
    if analysis.suggested_priority in ticket.Priority.values:
        ticket.priority = analysis.suggested_priority
        update_fields.append("priority")
    if analysis.suggested_tags:
        existing = [tag.strip() for tag in ticket.tags.split(",") if tag.strip()]
        for tag in analysis.suggested_tags:
            clean = str(tag).strip()
            if clean and clean not in existing:
                existing.append(clean)
        ticket.tags = ", ".join(existing)
        update_fields.append("tags")
    if update_fields:
        update_fields.append("updated_at")
        ticket.save(update_fields=update_fields)
    body = _internal_comment_body(analysis)
    TicketComment.objects.create(workspace=ticket.workspace, ticket=ticket, author=user, visibility=TicketComment.Visibility.INTERNAL, body=body)
    record_event(workspace=ticket.workspace, actor=user, ticket=ticket, event_type="ai.triage_applied", summary="AI triage applied", customer_visible=False)
    analysis.status = TicketAIAnalysis.Status.APPLIED
    analysis.applied_by = user
    analysis.applied_at = timezone.now()
    analysis.save(update_fields=["status", "applied_by", "applied_at", "updated_at"])
    return analysis


def _fail_analysis(analysis, code, message):
    analysis.status = TicketAIAnalysis.Status.FAILED
    analysis.error_code = code
    analysis.error_message = message[:2000]
    analysis.completed_at = timezone.now()
    analysis.save(update_fields=["status", "error_code", "error_message", "completed_at", "updated_at"])
    return analysis


def _internal_comment_body(analysis):
    tags = ", ".join(analysis.suggested_tags or []) or "No tags suggested"
    risks = "\n".join(f"- {risk}" for risk in analysis.risks) or "- No explicit risks listed"
    return (
        "AI triage applied.\n\n"
        f"Summary: {analysis.summary}\n\n"
        f"Suggested priority: {analysis.suggested_priority or 'No change'}\n"
        f"Suggested tags: {tags}\n\n"
        f"Solution draft:\n{analysis.solution_draft}\n\n"
        f"Risks:\n{risks}"
    )
