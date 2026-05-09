from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.permissions import require_internal_workspace
from crm.models import Organization
from tickets.models import Ticket

from .models import AIRun, CRMInsight, TimeEntrySuggestion, TicketAIAnalysis
from .services import apply_analysis, apply_selected_ticket_suggestions, approve_time_suggestion, create_queued_analysis, fail_analysis, generate_crm_insight, generate_workspace_digest, get_ai_settings, record_analysis_feedback, suggest_time_entry
from .tasks import analyze_ticket_with_ai, create_solution_snippet_with_ai


def ai_panel_context(ticket, workspace):
    return {
        "ticket": ticket,
        "ai_settings": get_ai_settings(workspace),
        "ai_analyses": ticket.ai_analyses.filter(workspace=workspace).select_related("requested_by", "applied_by")[:5],
        "reply_drafts": ticket.ai_reply_drafts.filter(workspace=workspace).select_related("approved_by")[:5],
        "time_suggestions": ticket.ai_time_suggestions.filter(workspace=workspace, user__isnull=False).select_related("user")[:5],
        "solution_snippets": ticket.solution_snippets.filter(workspace=workspace)[:5],
    }


@login_required
def ticket_ai_analyze(request, pk):
    workspace = require_internal_workspace(request.user)
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
def ticket_ai_apply(request, pk, analysis_id):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    analysis = get_object_or_404(TicketAIAnalysis, pk=analysis_id, workspace=workspace, ticket=ticket)
    try:
        apply_analysis(analysis, request.user)
        messages.info(request, "AI triage applied.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_ai_apply_selected(request, pk, analysis_id):
    workspace = require_internal_workspace(request.user)
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
def ticket_ai_feedback(request, pk, analysis_id):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    analysis = get_object_or_404(TicketAIAnalysis, pk=analysis_id, workspace=workspace, ticket=ticket)
    record_analysis_feedback(analysis, request.POST.get("feedback", ""))
    messages.info(request, "AI feedback recorded.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_ai_time_suggestion(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    if not get_ai_settings(workspace).time_suggestions_enabled:
        messages.error(request, "AI time suggestions are not enabled.")
        return redirect("ticket_detail", pk=ticket.pk)
    suggest_time_entry(ticket, request.user)
    messages.info(request, "Draft time suggestion created.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_ai_time_approve(request, pk, suggestion_id):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    suggestion = get_object_or_404(TimeEntrySuggestion, pk=suggestion_id, workspace=workspace, ticket=ticket, user=request.user)
    approve_time_suggestion(suggestion, request.user)
    messages.info(request, "AI time suggestion approved.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def ticket_ai_solution_memory(request, pk):
    workspace = require_internal_workspace(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, workspace=workspace)
    create_solution_snippet_with_ai.delay(str(ticket.pk), str(request.user.pk))
    messages.info(request, "Solution memory generation queued.")
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
def organization_ai_briefing(request, pk):
    workspace = require_internal_workspace(request.user)
    organization = get_object_or_404(Organization, pk=pk, workspace=workspace)
    if not get_ai_settings(workspace).crm_insights_enabled:
        messages.error(request, "AI CRM insights are not enabled.")
        return redirect("organization_detail", pk=organization.pk)
    generate_crm_insight(organization, request.user)
    messages.info(request, "AI account briefing generated.")
    return redirect("organization_detail", pk=organization.pk)


@login_required
def ai_audit(request):
    workspace = require_internal_workspace(request.user)
    runs = AIRun.objects.filter(workspace=workspace).select_related("requested_by")[:100]
    analyses = TicketAIAnalysis.objects.filter(workspace=workspace).select_related("ticket", "requested_by")[:50]
    return render(request, "ai/audit.html", {"runs": runs, "analyses": analyses})


@login_required
def workspace_ai_digest(request):
    workspace = require_internal_workspace(request.user)
    if not get_ai_settings(workspace).digest_enabled:
        messages.error(request, "AI workspace digests are not enabled.")
        return redirect("dashboard")
    generate_workspace_digest(workspace, request.user)
    messages.info(request, "AI workspace digest generated.")
    return redirect("ai_audit")
