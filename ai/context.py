import json
import re

from django.db.models import Count, Sum

from activity.models import ActivityEvent
from search.models import SearchDocument
from tickets.models import Ticket
from time_tracking.models import ActiveTimer, TimeEntry


SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|bearer)\b\s*[:=]\s*([^\s,;]+)"
)


def redact_secrets(value):
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value or "")


def build_ticket_context(ticket, ai_settings):
    workspace = ticket.workspace
    current = {
        "id": str(ticket.pk),
        "title": ticket.title,
        "description": redact_secrets(ticket.description),
        "status": ticket.status,
        "priority": ticket.priority,
        "tags": ticket.tags,
        "organization": ticket.organization.name if ticket.organization else "",
        "contact": ticket.contact.email if ticket.contact else "",
        "assignee": str(ticket.assignee) if ticket.assignee else "",
    }
    latest_comments = list(ticket.comments.filter(workspace=workspace).select_related("author").order_by("-created_at")[:12])
    comments = [
        {
            "id": str(comment.pk),
            "author": str(comment.author) if comment.author else "Customer",
            "visibility": comment.visibility,
            "body": redact_secrets(comment.body),
            "created_at": comment.created_at.isoformat(),
        }
        for comment in reversed(latest_comments)
    ]
    time_total = ticket.time_entries.filter(workspace=workspace).aggregate(total=Sum("duration_minutes"))["total"] or 0
    attachments = [
        {
            "id": str(attachment.pk),
            "name": attachment.display_name,
            "content_type": attachment.content_type,
            "size_bytes": attachment.size_bytes,
        }
        for attachment in ticket.attachments.filter(workspace=workspace)[:20]
    ]
    activity = [
        {"id": str(event.pk), "summary": event.summary, "created_at": event.created_at.isoformat()}
        for event in ActivityEvent.objects.filter(workspace=workspace, ticket=ticket).order_by("-created_at")[:10]
    ]
    historical = []
    if ticket.organization_id and ai_settings.max_historical_tickets:
        for historical_ticket in (
            Ticket.objects.filter(workspace=workspace, organization=ticket.organization)
            .exclude(pk=ticket.pk)
            .order_by("-updated_at")[: ai_settings.max_historical_tickets]
        ):
            historical.append(
                {
                    "id": str(historical_ticket.pk),
                    "title": historical_ticket.title,
                    "status": historical_ticket.status,
                    "priority": historical_ticket.priority,
                    "summary": redact_secrets(historical_ticket.description[:600]),
                }
            )
    search_refs = []
    if ticket.organization_id:
        for doc in SearchDocument.objects.filter(workspace=workspace, organization_id=ticket.organization_id).exclude(object_id=ticket.pk).order_by("-updated_at")[:5]:
            search_refs.append({"type": doc.entity_type, "id": str(doc.object_id), "title": doc.title, "snippet": redact_secrets(doc.body[:500])})
    approved_snippets = []
    try:
        for snippet in ticket.workspace.solution_snippets.filter(approved=True, ticket__organization_id=ticket.organization_id).order_by("-created_at")[:5]:
            approved_snippets.append({"id": str(snippet.pk), "title": snippet.title, "body": redact_secrets(snippet.body[:700]), "tags": snippet.tags})
    except AttributeError:
        approved_snippets = []
    return {
        "current_ticket": current,
        "comments": comments,
        "time_total_minutes": time_total,
        "attachments": attachments,
        "activity": activity,
        "historical_tickets": historical,
        "search_refs": search_refs,
        "approved_solution_snippets": approved_snippets,
    }


def build_analysis_messages(ticket, ai_settings):
    context = build_ticket_context(ticket, ai_settings)
    system = (
        "You are Threadline's internal support triage agent. "
        "Use only the provided workspace-scoped context. "
        "Do not claim to have performed actions. "
        "Return only valid JSON matching the provided schema. "
        "No markdown. No code fences. No prose outside JSON. "
        "Finish the JSON object completely. "
        "Keep summary to 1-2 sentences, solution_draft concise, risks to at most 5 items, client_context to at most 5 items, and context_refs to at most 8 items. "
        "Include customer_sentiment, urgency_reason, next_best_action, and similar_tickets when supported by context. "
        "Drafts are internal suggestions for support agents, never customer-visible."
    )
    context_json = json.dumps(context, separators=(",", ":"), ensure_ascii=False)
    user = (
        "Analyze this support ticket for triage and likely solution paths. "
        "Suggest priority, tags, useful historical context, risks, and an internal solution draft.\n\n"
        f"Context JSON:\n{context_json}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_reply_messages(ticket, ai_settings, intent, source_text=""):
    context = build_ticket_context(ticket, ai_settings)
    context["reply_intent"] = intent
    context["source_text"] = redact_secrets(source_text)
    return [
        {
            "role": "system",
            "content": (
                "You are Threadline's internal customer-reply drafting assistant. "
                "Use only provided workspace context. Return only valid JSON. "
                "Do not claim actions were completed. Keep the reply customer-safe, concise, and professional."
            ),
        },
        {"role": "user", "content": "Draft or transform a ticket reply.\n\nContext JSON:\n" + json.dumps(context, separators=(",", ":"), ensure_ascii=False)},
    ]


def build_crm_context(organization):
    workspace = organization.workspace
    tickets = Ticket.objects.filter(workspace=workspace, organization=organization).select_related("contact", "assignee").order_by("-updated_at")[:20]
    time_total = TimeEntry.objects.filter(workspace=workspace, organization=organization).aggregate(total=Sum("duration_minutes"))["total"] or 0
    return {
        "organization": {
            "id": str(organization.pk),
            "name": organization.name,
            "domain": organization.domain,
            "status": organization.status,
            "tier": organization.tier,
            "account_owner": organization.account_owner,
            "renewal_date": organization.renewal_date.isoformat() if organization.renewal_date else "",
            "health_score": organization.health_score,
            "notes": redact_secrets(organization.notes),
        },
        "contacts": [
            {"id": str(contact.pk), "name": contact.name, "email": contact.email, "title": contact.title}
            for contact in organization.contacts.filter(workspace=workspace)[:20]
        ],
        "tickets": [
            {
                "id": str(ticket.pk),
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "tags": ticket.tags,
                "description": redact_secrets(ticket.description[:500]),
                "updated_at": ticket.updated_at.isoformat(),
            }
            for ticket in tickets
        ],
        "time_total_minutes": time_total,
        "activity": [
            {"summary": event.summary, "created_at": event.created_at.isoformat()}
            for event in ActivityEvent.objects.filter(workspace=workspace, organization=organization)[:15]
        ],
    }


def build_crm_messages(organization):
    return [
        {
            "role": "system",
            "content": "You are Threadline's CRM support intelligence assistant. Return only valid JSON matching the schema. No markdown.",
        },
        {"role": "user", "content": "Create an internal account briefing from this workspace-scoped context.\n\nContext JSON:\n" + json.dumps(build_crm_context(organization), separators=(",", ":"), ensure_ascii=False)},
    ]


def build_time_context(ticket, user):
    workspace = ticket.workspace
    return {
        "ticket": {
            "id": str(ticket.pk),
            "title": ticket.title,
            "status": ticket.status,
            "priority": ticket.priority,
            "organization": ticket.organization.name if ticket.organization else "",
        },
        "agent_comments": [
            {"body": redact_secrets(comment.body[:500]), "created_at": comment.created_at.isoformat()}
            for comment in ticket.comments.filter(workspace=workspace, author=user).order_by("-created_at")[:10]
        ],
        "activity": [
            {"summary": event.summary, "created_at": event.created_at.isoformat()}
            for event in ActivityEvent.objects.filter(workspace=workspace, ticket=ticket, actor=user).order_by("-created_at")[:12]
        ],
        "existing_time_entries": [
            {"minutes": entry.duration_minutes, "notes": redact_secrets(entry.notes), "started_at": entry.started_at.isoformat()}
            for entry in ticket.time_entries.filter(workspace=workspace, user=user).order_by("-started_at")[:10]
        ],
        "active_timer": ActiveTimer.objects.filter(workspace=workspace, ticket=ticket, user=user).exists(),
    }


def build_time_messages(ticket, user):
    return [
        {"role": "system", "content": "You are Threadline's time tracking assistant. Return only valid JSON matching the schema. No markdown."},
        {"role": "user", "content": "Suggest one draft time entry from this activity context.\n\nContext JSON:\n" + json.dumps(build_time_context(ticket, user), separators=(",", ":"), ensure_ascii=False)},
    ]


def build_solution_messages(ticket, ai_settings):
    return [
        {"role": "system", "content": "You are Threadline's solution memory assistant. Return only valid JSON matching the schema. No markdown."},
        {"role": "user", "content": "Propose a reusable internal solution snippet from this resolved ticket.\n\nContext JSON:\n" + json.dumps(build_ticket_context(ticket, ai_settings), separators=(",", ":"), ensure_ascii=False)},
    ]


def find_unlogged_work(workspace, user, limit=12):
    tickets = (
        Ticket.objects.filter(workspace=workspace, comments__author=user)
        .annotate(agent_comment_count=Count("comments"), time_entry_count=Count("time_entries"))
        .filter(time_entry_count=0)
        .select_related("organization")
        .order_by("-updated_at")
        .distinct()[:limit]
    )
    return tickets
