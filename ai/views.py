from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.permissions import require_internal_workspace
from tickets.models import Ticket

from .models import AIProviderSettings, TicketAIAnalysis
from .services import apply_analysis, create_queued_analysis, get_ai_settings, run_ticket_analysis
from .tasks import analyze_ticket_with_ai


def ai_panel_context(ticket, workspace):
    return {
        "ticket": ticket,
        "ai_settings": get_ai_settings(workspace),
        "ai_analyses": ticket.ai_analyses.filter(workspace=workspace).select_related("requested_by", "applied_by")[:5],
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
    except Exception:
        run_ticket_analysis(analysis)
        messages.info(request, "AI analysis completed.")
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
