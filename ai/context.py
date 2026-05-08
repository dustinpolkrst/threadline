import re

from django.db.models import Sum

from activity.models import ActivityEvent
from search.models import SearchDocument
from tickets.models import Ticket


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
    comments = [
        {
            "id": str(comment.pk),
            "author": str(comment.author) if comment.author else "Customer",
            "visibility": comment.visibility,
            "body": redact_secrets(comment.body),
            "created_at": comment.created_at.isoformat(),
        }
        for comment in ticket.comments.filter(workspace=workspace).select_related("author")[:30]
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
        for event in ActivityEvent.objects.filter(workspace=workspace, ticket=ticket).order_by("-created_at")[:20]
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
        for doc in SearchDocument.objects.filter(workspace=workspace, organization_id=ticket.organization_id).exclude(object_id=ticket.pk).order_by("-updated_at")[:8]:
            search_refs.append({"type": doc.entity_type, "id": str(doc.object_id), "title": doc.title, "snippet": redact_secrets(doc.body[:500])})
    return {
        "current_ticket": current,
        "comments": comments,
        "time_total_minutes": time_total,
        "attachments": attachments,
        "activity": activity,
        "historical_tickets": historical,
        "search_refs": search_refs,
    }


def build_analysis_messages(ticket, ai_settings):
    context = build_ticket_context(ticket, ai_settings)
    system = (
        "You are Threadline's internal support triage agent. "
        "Use only the provided workspace-scoped context. "
        "Do not claim to have performed actions. "
        "Return only valid JSON matching the provided schema. "
        "No markdown. No code fences. No prose outside JSON. "
        "Drafts are internal suggestions for support agents, never customer-visible."
    )
    user = (
        "Analyze this support ticket for triage and likely solution paths. "
        "Suggest priority, tags, useful historical context, risks, and an internal solution draft.\n\n"
        f"Context:\n{context}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
