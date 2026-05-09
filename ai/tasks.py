from celery import shared_task

from crm.models import Organization
from tickets.models import Ticket
from workspaces.models import Workspace

from .models import TicketAIAnalysis, TimeEntrySuggestion
from .services import approve_time_suggestion, create_solution_snippet, generate_crm_insight, generate_workspace_digest, run_ticket_analysis, suggest_time_entry


@shared_task
def analyze_ticket_with_ai(analysis_id):
    analysis = TicketAIAnalysis.objects.select_related("workspace", "ticket").get(pk=analysis_id)
    run_ticket_analysis(analysis)
    return str(analysis.pk)


@shared_task
def generate_crm_insight_with_ai(organization_id, user_id=None):
    organization = Organization.objects.get(pk=organization_id)
    insight = generate_crm_insight(organization)
    return str(insight.pk)


@shared_task
def suggest_time_entry_with_ai(ticket_id, user_id):
    from django.contrib.auth import get_user_model

    ticket = Ticket.objects.get(pk=ticket_id)
    user = get_user_model().objects.get(pk=user_id)
    suggestion = suggest_time_entry(ticket, user)
    return str(suggestion.pk)


@shared_task
def generate_workspace_digest_with_ai(workspace_id, user_id=None):
    workspace = Workspace.objects.get(pk=workspace_id)
    digest = generate_workspace_digest(workspace)
    return str(digest.pk)


@shared_task
def create_solution_snippet_with_ai(ticket_id, user_id=None):
    ticket = Ticket.objects.get(pk=ticket_id)
    snippet = create_solution_snippet(ticket)
    return str(snippet.pk)
