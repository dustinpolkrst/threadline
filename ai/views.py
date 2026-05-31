from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import require_internal_workspace, require_support_workspace
from crm.models import Organization
from tickets.models import Ticket

from .models import AIRun, CRMInsight, QueueIntelligenceSnapshot, SolutionSnippet, TicketReplyDraft, TimeEntrySuggestion, TicketAIAnalysis
from .services import ai_usage_summary, approve_reply_draft, approve_solution_snippet, apply_analysis, apply_selected_ticket_suggestions, approve_time_suggestion, create_queued_analysis, fail_analysis, generate_workspace_digest, get_ai_settings, record_analysis_feedback, reject_solution_snippet, suggest_time_entry, time_cleanup_context
from .tasks import analyze_ticket_with_ai, build_queue_intelligence_with_ai, create_solution_snippet_with_ai, generate_crm_insight_with_ai, generate_reply_draft_with_ai


def ai_panel_context(ticket, workspace):
    return {
        "ticket": ticket,
        "ai_settings": get_ai_settings(workspace),
        "ai_analyses": ticket.ai_analyses.filter(workspace=workspace).select_related("requested_by", "applied_by")[:5],
        "reply_drafts": ticket.ai_reply_drafts.filter(workspace=workspace).select_related("approved_by")[:5],
        "time_suggestions": ticket.ai_time_suggestions.filter(workspace=workspace, user__isnull=False).select_related("user")[:5],
        "solution_snippets": ticket.solution_snippets.filter(workspace=workspace)[:5],
        "suggested_actions": ticket.ai_analyses.filter(workspace=workspace).prefetch_related("suggested_actions")[:5],
    }


@login_required
@require_POST
def ticket_ai_analyze(request, pk):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    ai_settings = get_ai_settings(workspace)
    if not ai_settings.enabled:
        messages.error(request, "AI is not enabled for this workspace.")
        return redirect("ticket_detail", pk=ticket.pk)
    mode = request.POST.get("mode") or TicketAIAnalysis.Mode.DRAFT
    if mode == TicketAIAnalysis.Mode.AUTO_TRIAGE and not ai_settings.auto_triage_enabled:
        mode = TicketAIAnalysis.Mode.DRAFT
    analysis = create_queued_analysis(ticket, request.user, mode=mode)
    try:
        analyze_ticket_with_ai.delay(str(analysis.pk))
        messages.info(request, "AI analysis queued.")
    except Exception as exc:
        fail_analysis(analysis, "queue_unavailable", f"AI analysis could not be queued. Confirm the Celery worker and broker are running. {exc}")
        messages.error(request, "AI analysis could not be queued. Confirm the Celery worker and broker are running.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_ai_panel(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    return render(request, "tickets/_ai_panel.html", ai_panel_context(ticket, workspace))


@login_required
@require_POST
def ticket_ai_apply(request, pk, analysis_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    analysis = get_object_or_404(TicketAIAnalysis, pk=analysis_id, workspace=workspace, ticket=ticket)
    try:
        apply_analysis(analysis, request.user)
        messages.info(request, "AI triage applied.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_apply_selected(request, pk, analysis_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    analysis = get_object_or_404(TicketAIAnalysis, pk=analysis_id, workspace=workspace, ticket=ticket)
    selected = request.POST.getlist("actions")
    try:
        applied = apply_selected_ticket_suggestions(analysis, request.user, selected)
        messages.info(request, f"Applied AI suggestions: {', '.join(applied) or 'none'}.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_feedback(request, pk, analysis_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    analysis = get_object_or_404(TicketAIAnalysis, pk=analysis_id, workspace=workspace, ticket=ticket)
    record_analysis_feedback(analysis, request.POST.get("feedback", ""))
    messages.info(request, "AI feedback recorded.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_time_suggestion(request, pk):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    if not get_ai_settings(workspace).time_suggestions_enabled:
        messages.error(request, "AI time suggestions are not enabled.")
        return redirect("ticket_detail", pk=ticket.pk)
    suggest_time_entry(ticket, request.user)
    messages.info(request, "Draft time suggestion created.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_time_approve(request, pk, suggestion_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    suggestion = get_object_or_404(TimeEntrySuggestion, pk=suggestion_id, workspace=workspace, ticket=ticket, user=request.user)
    approve_time_suggestion(suggestion, request.user)
    messages.info(request, "AI time suggestion approved.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_reply_draft(request, pk):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    if not get_ai_settings(workspace).reply_composer_enabled:
        messages.error(request, "AI reply composer is not enabled.")
        return redirect("ticket_detail", pk=ticket.pk)
    intent = request.POST.get("intent", "generate")
    source_text = request.POST.get("source_text", "")
    try:
        generate_reply_draft_with_ai.delay(str(ticket.pk), str(request.user.pk), intent, source_text)
        messages.info(request, "AI reply draft queued.")
    except Exception as exc:
        messages.error(request, f"AI reply draft could not be queued. {exc}")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_reply_approve(request, pk, draft_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    draft = get_object_or_404(TicketReplyDraft, pk=draft_id, workspace=workspace, ticket=ticket, audience=TicketReplyDraft.Audience.CUSTOMER)
    approve_reply_draft(draft, request.user)
    messages.info(request, "AI reply draft approved and posted as a public comment.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_solution_memory(request, pk):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    create_solution_snippet_with_ai.delay(str(ticket.pk), str(request.user.pk))
    messages.info(request, "Solution memory generation queued.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_ai_solution_decision(request, pk, snippet_id):
    workspace = require_support_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    snippet = get_object_or_404(SolutionSnippet, pk=snippet_id, workspace=workspace, ticket=ticket)
    if request.POST.get("decision") == "approve":
        approve_solution_snippet(snippet, request.user)
        messages.info(request, "Solution memory approved and indexed.")
    else:
        reject_solution_snippet(snippet, request.user)
        messages.info(request, "Solution memory rejected.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def organization_ai_briefing(request, pk):
    workspace = require_support_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    if not get_ai_settings(workspace).crm_insights_enabled:
        messages.error(request, "AI CRM insights are not enabled.")
        return redirect("organization_detail", pk=organization.pk)
    try:
        generate_crm_insight_with_ai.delay(str(organization.pk), str(request.user.pk))
        messages.info(request, "AI account briefing queued.")
    except Exception as exc:
        messages.error(request, f"AI account briefing could not be queued. {exc}")
    return redirect("organization_detail", pk=organization.pk)


@login_required
def ai_audit(request):
    workspace = require_internal_workspace(request.user)
    runs = AIRun.objects.filter(workspace=workspace).select_related("requested_by")[:100]
    analyses = TicketAIAnalysis.objects.filter(workspace=workspace).select_related("ticket", "requested_by")[:50]
    actions = workspace.ai_suggested_actions.select_related("applied_by", "run")[:100]
    snippets = SolutionSnippet.objects.filter(workspace=workspace).select_related("ticket")[:50]
    return render(request, "ai/audit.html", {"runs": runs, "analyses": analyses, "actions": actions, "snippets": snippets, "ai_usage": ai_usage_summary(workspace)})


@login_required
@require_POST
def workspace_ai_digest(request):
    workspace = require_support_workspace(request.user)
    if not get_ai_settings(workspace).digest_enabled:
        messages.error(request, "AI workspace digests are not enabled.")
        return redirect("dashboard")
    generate_workspace_digest(workspace, request.user)
    messages.info(request, "AI workspace digest generated.")
    return redirect("ai_audit")


@login_required
@require_POST
def workspace_ai_queue_intelligence(request):
    workspace = require_support_workspace(request.user)
    if not get_ai_settings(workspace).queue_intelligence_enabled:
        messages.error(request, "AI queue intelligence is not enabled.")
        return redirect("dashboard")
    try:
        build_queue_intelligence_with_ai.delay(str(workspace.pk), str(request.user.pk))
        messages.info(request, "AI queue intelligence refresh queued.")
    except Exception as exc:
        messages.error(request, f"AI queue intelligence could not be queued. {exc}")
    return redirect("dashboard")


@login_required
def time_ai_cleanup(request):
    workspace = require_internal_workspace(request.user)
    return render(request, "ai/time_cleanup.html", time_cleanup_context(workspace, request.user))
