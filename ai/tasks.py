from celery import shared_task

from crm.models import Organization
from tickets.models import Ticket
from workspaces.models import Workspace

from .models import TicketAIAnalysis
from .services import build_queue_intelligence, create_solution_snippet, generate_crm_insight, generate_reply_draft, generate_workspace_digest, prune_ai_generation_retention, run_ticket_analysis, suggest_time_entry


@shared_task
def analyze_ticket_with_ai(analysis_id):
    analysis = TicketAIAnalysis.objects.select_related("workspace", "ticket").get(pk=analysis_id)
    run_ticket_analysis(analysis)
    return str(analysis.pk)


@shared_task
def generate_crm_insight_with_ai(organization_id, user_id=None):
    from django.contrib.auth import get_user_model

    organization = Organization.objects.get(pk=organization_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    insight = generate_crm_insight(organization, user)
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
    from django.contrib.auth import get_user_model

    workspace = Workspace.objects.get(pk=workspace_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    digest = generate_workspace_digest(workspace, user)
    return str(digest.pk)


@shared_task
def create_solution_snippet_with_ai(ticket_id, user_id=None):
    from django.contrib.auth import get_user_model

    ticket = Ticket.objects.get(pk=ticket_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    snippet = create_solution_snippet(ticket, user)
    return str(snippet.pk)


@shared_task
def generate_reply_draft_with_ai(ticket_id, user_id, intent="generate", source_text=""):
    from django.contrib.auth import get_user_model

    ticket = Ticket.objects.get(pk=ticket_id)
    user = get_user_model().objects.get(pk=user_id)
    draft = generate_reply_draft(ticket, user, intent=intent, source_text=source_text)
    return str(draft.pk)


@shared_task
def build_queue_intelligence_with_ai(workspace_id, user_id=None):
    from django.contrib.auth import get_user_model

    workspace = Workspace.objects.get(pk=workspace_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    snapshot = build_queue_intelligence(workspace, user)
    return str(snapshot.pk)


@shared_task
def prune_ai_generation_retention_task():
    return prune_ai_generation_retention()
