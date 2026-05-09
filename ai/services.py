from django.utils import timezone
from django.conf import settings

from activity.services import record_event
from crm.models import Contact, Organization
from search.services import index_comment, index_ticket
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry

from .client import OpenRouterError, parse_analysis_response, send_chat_completion
from .context import build_analysis_messages
from .models import AIRun, AISuggestedAction, AIProviderSettings, CRMInsight, SolutionSnippet, TicketAIAnalysis, TicketReplyDraft, TimeEntrySuggestion, WorkspaceDigest


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
        return fail_analysis(analysis, "disabled", "AI is not enabled for this workspace.")
    try:
        messages = build_analysis_messages(analysis.ticket, ai_settings)
        response = send_chat_completion(ai_settings, messages, max_tokens=settings.OPENROUTER_ANALYSIS_MAX_TOKENS)
        parsed, usage = parse_analysis_response(response)
    except OpenRouterError as exc:
        return fail_analysis(analysis, exc.code, str(exc))

    triage = parsed.get("triage") or {}
    analysis.summary = parsed.get("summary", "")
    analysis.suggested_priority = triage.get("priority", "")
    analysis.suggested_status = triage.get("status", "")
    analysis.suggested_tags = triage.get("tags") or []
    analysis.suggested_assignee_reason = triage.get("assignee_reason", "")
    analysis.solution_draft = parsed.get("solution_draft", "")
    analysis.customer_reply_draft = parsed.get("customer_reply_draft", "")
    analysis.internal_note_draft = parsed.get("internal_note_draft", "")
    analysis.root_cause_notes = parsed.get("root_cause_notes", "")
    analysis.missing_info = parsed.get("missing_info") or []
    analysis.escalation_risk = parsed.get("escalation_risk", "")
    analysis.next_actions = parsed.get("next_actions") or []
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
    _sync_ticket_workbench_artifacts(analysis)
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
        index_ticket(ticket)
    body = _internal_comment_body(analysis)
    comment = TicketComment.objects.create(workspace=ticket.workspace, ticket=ticket, author=user, visibility=TicketComment.Visibility.INTERNAL, body=body)
    index_comment(comment)
    record_event(workspace=ticket.workspace, actor=user, ticket=ticket, event_type="ai.triage_applied", summary="AI triage applied", customer_visible=False)
    analysis.status = TicketAIAnalysis.Status.APPLIED
    analysis.applied_by = user
    analysis.applied_at = timezone.now()
    analysis.save(update_fields=["status", "applied_by", "applied_at", "updated_at"])
    return analysis


def apply_selected_ticket_suggestions(analysis, user, selected_actions):
    ai_settings = get_ai_settings(analysis.workspace)
    if analysis.status not in [TicketAIAnalysis.Status.SUCCEEDED, TicketAIAnalysis.Status.APPLIED]:
        raise ValueError("Only successful AI analyses can be applied.")
    ticket = analysis.ticket
    update_fields = []
    applied = []
    if "priority" in selected_actions and analysis.suggested_priority in ticket.Priority.values:
        ticket.priority = analysis.suggested_priority
        update_fields.append("priority")
        applied.append("priority")
    if "status" in selected_actions and analysis.suggested_status in ticket.Status.values:
        ticket.status = analysis.suggested_status
        update_fields.append("status")
        applied.append("status")
    if "tags" in selected_actions and analysis.suggested_tags:
        existing = [tag.strip() for tag in ticket.tags.split(",") if tag.strip()]
        for tag in analysis.suggested_tags:
            clean = str(tag).strip()
            if clean and clean not in existing:
                existing.append(clean)
        ticket.tags = ", ".join(existing)
        update_fields.append("tags")
        applied.append("tags")
    if update_fields:
        update_fields.append("updated_at")
        ticket.save(update_fields=update_fields)
        index_ticket(ticket)
    if "internal_note" in selected_actions and analysis.internal_note_draft:
        comment = TicketComment.objects.create(workspace=ticket.workspace, ticket=ticket, author=user, visibility=TicketComment.Visibility.INTERNAL, body=analysis.internal_note_draft)
        index_comment(comment)
        applied.append("internal_note")
    if "customer_reply" in selected_actions and analysis.customer_reply_draft:
        draft = TicketReplyDraft.objects.filter(workspace=ticket.workspace, ticket=ticket, analysis=analysis, audience=TicketReplyDraft.Audience.CUSTOMER).first()
        if draft:
            draft.status = TicketReplyDraft.Status.APPROVED
            draft.approved_by = user
            draft.approved_at = timezone.now()
            draft.save(update_fields=["status", "approved_by", "approved_at"])
        applied.append("customer_reply")
    AISuggestedAction.objects.filter(workspace=ticket.workspace, ticket_analysis=analysis, action_type__in=applied).update(status=AISuggestedAction.Status.APPLIED, applied_by=user, applied_at=timezone.now())
    if applied:
        record_event(workspace=ticket.workspace, actor=user, ticket=ticket, event_type="ai.suggestions_applied", summary=f"Applied AI suggestions: {', '.join(applied)}", customer_visible=False)
    analysis.status = TicketAIAnalysis.Status.APPLIED
    analysis.applied_by = user
    analysis.applied_at = timezone.now()
    analysis.save(update_fields=["status", "applied_by", "applied_at", "updated_at"])
    return applied


def record_analysis_feedback(analysis, feedback):
    if feedback in ["accepted", "edited", "rejected", "wrong_context"]:
        analysis.feedback = feedback
        analysis.save(update_fields=["feedback", "updated_at"])
        AISuggestedAction.objects.filter(workspace=analysis.workspace, ticket_analysis=analysis, status=AISuggestedAction.Status.PENDING).update(status=AISuggestedAction.Status.REJECTED if feedback in ["rejected", "wrong_context"] else AISuggestedAction.Status.PENDING)
    return analysis


def generate_crm_insight(organization, user=None):
    run = _start_run(organization.workspace, AIRun.Workflow.CRM_INSIGHT, "organization", organization.pk, user)
    tickets = Ticket.objects.filter(workspace=organization.workspace, organization=organization).order_by("-updated_at")
    open_count = tickets.filter(status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).count()
    urgent_count = tickets.filter(priority=Ticket.Priority.URGENT).count()
    recent_titles = list(tickets.values_list("title", flat=True)[:5])
    summary = f"{organization.name} has {open_count} open tickets and {urgent_count} urgent tickets. Recent themes: {', '.join(recent_titles) or 'none yet'}."
    risks = []
    if urgent_count:
        risks.append("Urgent workload exists for this account.")
    if organization.status == Organization.Status.AT_RISK:
        risks.append("Account is already marked at risk.")
    suggestions = ["Review recent open tickets before responding.", "Confirm owner and renewal context are current."]
    insight = CRMInsight.objects.create(workspace=organization.workspace, organization=organization, run=run, summary=summary, recurring_issues=recent_titles, risks=risks, suggestions=suggestions)
    _finish_run(run, {"summary": summary, "risks": risks, "suggestions": suggestions})
    return insight


def suggest_time_entry(ticket, user):
    run = _start_run(ticket.workspace, AIRun.Workflow.TIME_SUGGESTION, "ticket", ticket.pk, user)
    comment_count = ticket.comments.filter(workspace=ticket.workspace, author=user).count()
    minutes = max(15, min(120, 15 + comment_count * 10))
    suggestion = TimeEntrySuggestion.objects.create(workspace=ticket.workspace, ticket=ticket, user=user, run=run, suggested_minutes=minutes, billable=True, notes=f"Suggested from ticket activity on {ticket.title}.")
    _finish_run(run, {"suggested_minutes": minutes, "ticket": str(ticket.pk)})
    return suggestion


def approve_time_suggestion(suggestion, user):
    entry = TimeEntry.objects.create(
        workspace=suggestion.workspace,
        user=user,
        ticket=suggestion.ticket,
        organization=suggestion.ticket.organization,
        contact=suggestion.ticket.contact,
        started_at=timezone.now(),
        duration_minutes=suggestion.suggested_minutes,
        billable=suggestion.billable,
        customer_visible=False,
        notes=suggestion.notes,
    )
    suggestion.status = TimeEntrySuggestion.Status.APPROVED
    suggestion.created_time_entry = entry
    suggestion.save(update_fields=["status", "created_time_entry"])
    record_event(workspace=suggestion.workspace, actor=user, ticket=suggestion.ticket, event_type="ai.time_suggestion_approved", summary=f"Approved AI time suggestion for {entry.duration_minutes} minutes", customer_visible=False)
    return entry


def generate_workspace_digest(workspace, user=None):
    today = timezone.localdate()
    start = today - timezone.timedelta(days=7)
    run = _start_run(workspace, AIRun.Workflow.WORKSPACE_DIGEST, "workspace", workspace.pk, user)
    tickets = Ticket.objects.filter(workspace=workspace, updated_at__date__gte=start)
    open_count = tickets.filter(status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).count()
    urgent_count = tickets.filter(priority=Ticket.Priority.URGENT).count()
    themes = list(tickets.exclude(tags="").values_list("tags", flat=True)[:10])
    summary = f"Last 7 days: {tickets.count()} updated tickets, {open_count} open, {urgent_count} urgent."
    digest = WorkspaceDigest.objects.create(workspace=workspace, run=run, period_start=start, period_end=today, summary=summary, themes=themes, accounts_at_risk=[], time_insights=[], suggestions=["Review stale pending tickets.", "Check urgent queue before the next customer update."])
    _finish_run(run, {"summary": summary, "themes": themes})
    return digest


def create_solution_snippet(ticket, user=None):
    run = _start_run(ticket.workspace, AIRun.Workflow.SOLUTION_MEMORY, "ticket", ticket.pk, user)
    latest_public = ticket.comments.filter(workspace=ticket.workspace, visibility=TicketComment.Visibility.PUBLIC).order_by("-created_at").first()
    body = latest_public.body if latest_public else ticket.description
    title = f"Resolution pattern: {ticket.title[:120]}"
    snippet = SolutionSnippet.objects.create(workspace=ticket.workspace, ticket=ticket, run=run, title=title, body=body[:1200], tags=[tag.strip() for tag in ticket.tags.split(",") if tag.strip()])
    _finish_run(run, {"title": title})
    return snippet


def fail_analysis(analysis, code, message):
    analysis.status = TicketAIAnalysis.Status.FAILED
    analysis.error_code = code
    analysis.error_message = message[:2000]
    analysis.completed_at = timezone.now()
    analysis.save(update_fields=["status", "error_code", "error_message", "completed_at", "updated_at"])
    return analysis


def _sync_ticket_workbench_artifacts(analysis):
    run = AIRun.objects.create(
        workspace=analysis.workspace,
        workflow=AIRun.Workflow.TICKET_WORKBENCH,
        status=AIRun.Status.SUCCEEDED,
        subject_type="ticket",
        subject_id=analysis.ticket_id,
        requested_by=analysis.requested_by,
        output={
            "summary": analysis.summary,
            "root_cause_notes": analysis.root_cause_notes,
            "missing_info": analysis.missing_info,
            "next_actions": analysis.next_actions,
            "escalation_risk": analysis.escalation_risk,
        },
        context_refs=analysis.context_refs,
        raw_model=analysis.raw_model,
        prompt_tokens=analysis.prompt_tokens,
        completion_tokens=analysis.completion_tokens,
        total_tokens=analysis.total_tokens,
        completed_at=timezone.now(),
    )
    actions = []
    if analysis.suggested_priority:
        actions.append(("priority", f"Set priority to {analysis.suggested_priority}", {"priority": analysis.suggested_priority}))
    if analysis.suggested_status:
        actions.append(("status", f"Set status to {analysis.suggested_status}", {"status": analysis.suggested_status}))
    if analysis.suggested_tags:
        actions.append(("tags", "Add suggested tags", {"tags": analysis.suggested_tags}))
    if analysis.internal_note_draft:
        actions.append(("internal_note", "Create internal note", {"body": analysis.internal_note_draft}))
    if analysis.customer_reply_draft:
        actions.append(("customer_reply", "Approve customer reply draft", {"body": analysis.customer_reply_draft}))
    for action_type, title, payload in actions:
        AISuggestedAction.objects.create(workspace=analysis.workspace, run=run, ticket_analysis=analysis, action_type=action_type, title=title, payload=payload)
    if analysis.customer_reply_draft:
        TicketReplyDraft.objects.create(workspace=analysis.workspace, ticket=analysis.ticket, run=run, analysis=analysis, audience=TicketReplyDraft.Audience.CUSTOMER, body=analysis.customer_reply_draft)
    if analysis.internal_note_draft:
        TicketReplyDraft.objects.create(workspace=analysis.workspace, ticket=analysis.ticket, run=run, analysis=analysis, audience=TicketReplyDraft.Audience.INTERNAL, body=analysis.internal_note_draft)
    return run


def _start_run(workspace, workflow, subject_type, subject_id, user=None):
    return AIRun.objects.create(workspace=workspace, workflow=workflow, status=AIRun.Status.RUNNING, subject_type=subject_type, subject_id=subject_id, requested_by=user)


def _finish_run(run, output):
    run.status = AIRun.Status.SUCCEEDED
    run.output = output
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "output", "completed_at", "updated_at"])
    return run


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
