import time

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.conf import settings

from activity.services import record_event
from crm.models import Contact, Organization
from search.services import index_comment, index_solution_snippet, index_ticket
from tickets.models import Ticket, TicketComment, TicketRelation
from time_tracking.models import TimeEntry

from .client import OpenRouterError, crm_insight_schema, parse_analysis_response, parse_structured_response, reply_schema, send_chat_completion, solution_snippet_schema, time_suggestion_schema
from .context import build_analysis_messages, build_crm_messages, build_reply_messages, build_solution_messages, build_time_messages, find_unlogged_work
from .models import AIRun, AISuggestedAction, AIProviderSettings, CRMInsight, QueueIntelligenceSnapshot, SolutionSnippet, TicketAIAnalysis, TicketReplyDraft, TimeEntrySuggestion, WorkspaceDigest


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
    analysis.customer_sentiment = parsed.get("customer_sentiment", "")
    analysis.urgency_reason = parsed.get("urgency_reason", "")
    analysis.next_best_action = parsed.get("next_best_action", "")
    analysis.similar_tickets = parsed.get("similar_tickets") or []
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
            comment = TicketComment.objects.create(workspace=ticket.workspace, ticket=ticket, author=user, visibility=TicketComment.Visibility.PUBLIC, body=draft.body)
            index_comment(comment)
        applied.append("customer_reply")
    AISuggestedAction.objects.filter(workspace=ticket.workspace, ticket_analysis=analysis, action_type__in=applied).update(status=AISuggestedAction.Status.APPLIED, applied_by=user, applied_at=timezone.now())
    if applied:
        record_event(workspace=ticket.workspace, actor=user, ticket=ticket, event_type="ai.suggestions_applied", summary=f"Applied AI suggestions: {', '.join(applied)}", customer_visible=False)
    analysis.status = TicketAIAnalysis.Status.APPLIED
    analysis.applied_by = user
    analysis.applied_at = timezone.now()
    analysis.save(update_fields=["status", "applied_by", "applied_at", "updated_at"])
    return applied


def generate_reply_draft(ticket, user, intent="generate", source_text=""):
    ai_settings = get_ai_settings(ticket.workspace)
    if not ai_settings.enabled or not ai_settings.reply_composer_enabled:
        raise ValueError("AI reply composer is not enabled.")
    run = _start_run(ticket.workspace, AIRun.Workflow.REPLY_COMPOSER, "ticket", ticket.pk, user)
    started = time.monotonic()
    try:
        response = send_chat_completion(ai_settings, build_reply_messages(ticket, ai_settings, intent, source_text), max_tokens=1200, response_format=reply_schema())
        parsed, usage = parse_structured_response(response)
    except OpenRouterError as exc:
        _fail_run(run, exc.code, str(exc))
        raise
    draft = TicketReplyDraft.objects.create(
        workspace=ticket.workspace,
        ticket=ticket,
        run=run,
        audience=TicketReplyDraft.Audience.CUSTOMER,
        body=parsed.get("body", ""),
        prompt=f"{intent}: {source_text}"[:2000],
    )
    _finish_run(run, {"body": draft.body, "reason": parsed.get("reason", "")}, usage=usage, latency_ms=_elapsed_ms(started))
    AISuggestedAction.objects.create(workspace=ticket.workspace, run=run, action_type="customer_reply", title="Approve customer reply draft", payload={"draft_id": str(draft.pk)})
    return draft


def approve_reply_draft(draft, user):
    if draft.status != TicketReplyDraft.Status.DRAFT:
        return draft
    comment = TicketComment.objects.create(workspace=draft.workspace, ticket=draft.ticket, author=user, visibility=TicketComment.Visibility.PUBLIC, body=draft.body)
    index_comment(comment)
    draft.status = TicketReplyDraft.Status.APPROVED
    draft.approved_by = user
    draft.approved_at = timezone.now()
    draft.save(update_fields=["status", "approved_by", "approved_at"])
    AISuggestedAction.objects.filter(workspace=draft.workspace, run=draft.run, action_type="customer_reply").update(status=AISuggestedAction.Status.APPLIED, applied_by=user, applied_at=timezone.now())
    record_event(workspace=draft.workspace, actor=user, ticket=draft.ticket, event_type="ai.reply_approved", summary="Approved AI customer reply draft", customer_visible=False)
    return draft


def record_analysis_feedback(analysis, feedback):
    if feedback in ["accepted", "edited", "rejected", "wrong_context"]:
        analysis.feedback = feedback
        analysis.save(update_fields=["feedback", "updated_at"])
        AISuggestedAction.objects.filter(workspace=analysis.workspace, ticket_analysis=analysis, status=AISuggestedAction.Status.PENDING).update(status=AISuggestedAction.Status.REJECTED if feedback in ["rejected", "wrong_context"] else AISuggestedAction.Status.PENDING)
    return analysis


def generate_crm_insight(organization, user=None):
    run = _start_run(organization.workspace, AIRun.Workflow.CRM_INSIGHT, "organization", organization.pk, user)
    ai_settings = get_ai_settings(organization.workspace)
    if not ai_settings.enabled or not ai_settings.crm_insights_enabled or not ai_settings.has_api_key:
        return _heuristic_crm_insight(organization, run)
    started = time.monotonic()
    try:
        response = send_chat_completion(ai_settings, build_crm_messages(organization), max_tokens=1800, response_format=crm_insight_schema())
        parsed, usage = parse_structured_response(response)
    except OpenRouterError as exc:
        _fail_run(run, exc.code, str(exc))
        raise
    insight = CRMInsight.objects.create(
        workspace=organization.workspace,
        organization=organization,
        run=run,
        summary=parsed.get("summary", ""),
        support_tone=parsed.get("support_tone", ""),
        recommended_next_touch=parsed.get("recommended_next_touch", ""),
        recurring_issues=parsed.get("recurring_issues") or [],
        product_areas=parsed.get("product_areas") or [],
        risks=parsed.get("risks") or [],
        suggestions=parsed.get("suggestions") or [],
        hygiene_suggestions=parsed.get("hygiene_suggestions") or [],
    )
    _finish_run(run, parsed, usage=usage, latency_ms=_elapsed_ms(started))
    return insight


def _heuristic_crm_insight(organization, run):
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
    hygiene = []
    if not organization.domain:
        hygiene.append("Add an account domain.")
    if not organization.billing_email:
        hygiene.append("Add a billing email.")
    suggestions = ["Review recent open tickets before responding.", "Confirm owner and renewal context are current."]
    insight = CRMInsight.objects.create(workspace=organization.workspace, organization=organization, run=run, summary=summary, support_tone="unknown", recommended_next_touch="Review recent support history before the next reply.", recurring_issues=recent_titles, risks=risks, suggestions=suggestions, hygiene_suggestions=hygiene)
    _finish_run(run, {"summary": summary, "risks": risks, "suggestions": suggestions, "hygiene_suggestions": hygiene})
    return insight


def suggest_time_entry(ticket, user):
    run = _start_run(ticket.workspace, AIRun.Workflow.TIME_SUGGESTION, "ticket", ticket.pk, user)
    ai_settings = get_ai_settings(ticket.workspace)
    if ai_settings.enabled and ai_settings.time_suggestions_enabled and ai_settings.has_api_key:
        started = time.monotonic()
        try:
            response = send_chat_completion(ai_settings, build_time_messages(ticket, user), max_tokens=800, response_format=time_suggestion_schema())
            parsed, usage = parse_structured_response(response)
            minutes = int(parsed.get("minutes") or 15)
            suggestion = TimeEntrySuggestion.objects.create(workspace=ticket.workspace, ticket=ticket, user=user, run=run, suggested_minutes=max(1, min(minutes, 480)), billable=bool(parsed.get("billable", True)), notes=parsed.get("notes", ""), reason=parsed.get("reason", ""))
            _finish_run(run, parsed, usage=usage, latency_ms=_elapsed_ms(started))
            return suggestion
        except OpenRouterError as exc:
            _fail_run(run, exc.code, str(exc))
            raise
    comment_count = ticket.comments.filter(workspace=ticket.workspace, author=user).count()
    minutes = max(15, min(120, 15 + comment_count * 10))
    suggestion = TimeEntrySuggestion.objects.create(workspace=ticket.workspace, ticket=ticket, user=user, run=run, suggested_minutes=minutes, billable=True, notes=f"Suggested from ticket activity on {ticket.title}.", reason="Estimated from recent agent comments because provider generation is unavailable.")
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
    ai_settings = get_ai_settings(ticket.workspace)
    if ai_settings.enabled and ai_settings.solution_memory_enabled and ai_settings.has_api_key:
        started = time.monotonic()
        try:
            response = send_chat_completion(ai_settings, build_solution_messages(ticket, ai_settings), max_tokens=1000, response_format=solution_snippet_schema())
            parsed, usage = parse_structured_response(response)
            snippet = SolutionSnippet.objects.create(workspace=ticket.workspace, ticket=ticket, run=run, title=parsed.get("title", "")[:180], body=parsed.get("body", ""), tags=parsed.get("tags") or [])
            _finish_run(run, parsed, usage=usage, latency_ms=_elapsed_ms(started))
            return snippet
        except OpenRouterError as exc:
            _fail_run(run, exc.code, str(exc))
            raise
    latest_public = ticket.comments.filter(workspace=ticket.workspace, visibility=TicketComment.Visibility.PUBLIC).order_by("-created_at").first()
    body = latest_public.body if latest_public else ticket.description
    title = f"Resolution pattern: {ticket.title[:120]}"
    snippet = SolutionSnippet.objects.create(workspace=ticket.workspace, ticket=ticket, run=run, title=title, body=body[:1200], tags=[tag.strip() for tag in ticket.tags.split(",") if tag.strip()])
    _finish_run(run, {"title": title})
    return snippet


def approve_solution_snippet(snippet, user):
    snippet.approved = True
    snippet.save(update_fields=["approved"])
    index_solution_snippet(snippet)
    AISuggestedAction.objects.create(workspace=snippet.workspace, run=snippet.run, action_type="solution_snippet", title="Approved solution memory", payload={"snippet_id": str(snippet.pk)}, status=AISuggestedAction.Status.APPLIED, applied_by=user, applied_at=timezone.now())
    record_event(workspace=snippet.workspace, actor=user, ticket=snippet.ticket, event_type="ai.solution_approved", summary=f"Approved solution memory: {snippet.title}", customer_visible=False)
    return snippet


def reject_solution_snippet(snippet, user):
    snippet.approved = False
    snippet.save(update_fields=["approved"])
    AISuggestedAction.objects.create(workspace=snippet.workspace, run=snippet.run, action_type="solution_snippet", title="Rejected solution memory", payload={"snippet_id": str(snippet.pk)}, status=AISuggestedAction.Status.REJECTED, applied_by=user, applied_at=timezone.now())
    return snippet


def build_queue_intelligence(workspace, user=None):
    run = _start_run(workspace, AIRun.Workflow.QUEUE_INTELLIGENCE, "workspace", workspace.pk, user)
    now = timezone.now()
    open_tickets = Ticket.objects.filter(workspace=workspace, status__in=[Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]).select_related("organization")
    likely_urgent = [_ticket_card(ticket, "Urgent priority or urgent language") for ticket in open_tickets.filter(Q(priority=Ticket.Priority.URGENT) | Q(title__icontains="urgent") | Q(description__icontains="urgent"))[:8]]
    stale_pending = [_ticket_card(ticket, "Pending for more than two days") for ticket in open_tickets.filter(status=Ticket.Status.PENDING, waiting_since__lte=now - timezone.timedelta(days=2))[:8]]
    missing_customer_info = [_ticket_card(ticket, "Missing organization or contact") for ticket in open_tickets.filter(Q(organization__isnull=True) | Q(contact__isnull=True))[:8]]
    sla_risks = [_ticket_card(ticket, "SLA due within one hour or already breached") for ticket in open_tickets.filter(Q(next_response_due_at__lte=now + timezone.timedelta(hours=1)) | Q(first_response_due_at__lte=now + timezone.timedelta(hours=1)))[:8]]
    high_effort_accounts = [
        {"organization": row["organization__name"] or "Unassigned", "minutes": row["minutes"] or 0, "ticket_count": row["tickets"], "reason": "High recent ticket/time volume"}
        for row in Ticket.objects.filter(workspace=workspace, updated_at__gte=now - timezone.timedelta(days=14)).values("organization__name").annotate(tickets=Count("id"), minutes=Sum("time_entries__duration_minutes")).order_by("-minutes", "-tickets")[:6]
    ]
    probable_duplicates = []
    seen = {}
    for ticket in open_tickets.order_by("-updated_at")[:80]:
        key = ticket.title.lower().strip()[:40]
        if key in seen and key:
            probable_duplicates.append({"ticket": str(ticket.pk), "title": ticket.title, "matched_ticket": str(seen[key].pk), "reason": "Similar title in open queue"})
        else:
            seen[key] = ticket
        if len(probable_duplicates) >= 8:
            break
    snapshot = QueueIntelligenceSnapshot.objects.create(workspace=workspace, run=run, likely_urgent=likely_urgent, stale_pending=stale_pending, missing_customer_info=missing_customer_info, probable_duplicates=probable_duplicates, sla_risks=sla_risks, high_effort_accounts=high_effort_accounts)
    _finish_run(run, {"likely_urgent": likely_urgent, "stale_pending": stale_pending, "missing_customer_info": missing_customer_info, "probable_duplicates": probable_duplicates, "sla_risks": sla_risks, "high_effort_accounts": high_effort_accounts})
    return snapshot


def time_cleanup_context(workspace, user):
    return {
        "unlogged_tickets": find_unlogged_work(workspace, user),
        "draft_suggestions": TimeEntrySuggestion.objects.filter(workspace=workspace, user=user, status=TimeEntrySuggestion.Status.DRAFT).select_related("ticket", "ticket__organization")[:25],
    }


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
            "customer_sentiment": analysis.customer_sentiment,
            "urgency_reason": analysis.urgency_reason,
            "next_best_action": analysis.next_best_action,
            "similar_tickets": analysis.similar_tickets,
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
        provider_generation_id="",
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


def _finish_run(run, output, usage=None, latency_ms=0):
    run.status = AIRun.Status.SUCCEEDED
    run.output = output
    if usage:
        run.raw_model = usage.get("raw_model", "")
        run.prompt_tokens = usage.get("prompt_tokens", 0)
        run.completion_tokens = usage.get("completion_tokens", 0)
        run.total_tokens = usage.get("total_tokens", 0)
        run.provider_generation_id = usage.get("provider_generation_id", "")
    run.latency_ms = latency_ms
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "output", "raw_model", "prompt_tokens", "completion_tokens", "total_tokens", "provider_generation_id", "latency_ms", "completed_at", "updated_at"])
    return run


def _fail_run(run, code, message):
    run.status = AIRun.Status.FAILED
    run.error_code = code
    run.error_message = message[:2000]
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error_code", "error_message", "completed_at", "updated_at"])
    return run


def _elapsed_ms(started):
    return max(0, int((time.monotonic() - started) * 1000))


def _ticket_card(ticket, reason):
    return {"id": str(ticket.pk), "title": ticket.title, "organization": ticket.organization.name if ticket.organization else "", "priority": ticket.priority, "status": ticket.status, "reason": reason}


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
