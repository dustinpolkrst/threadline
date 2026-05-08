from django.utils import timezone
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo
from .models import Ticket, TicketRelation


OPEN_STATUSES = [Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]


def apply_initial_sla(ticket):
    now = timezone.now()
    first, next_response, _resolution = targets_for(ticket)
    ticket.first_response_due_at = add_business_minutes(ticket.workspace, now, first)
    ticket.next_response_due_at = add_business_minutes(ticket.workspace, now, next_response)
    return ticket


def mark_agent_reply(ticket):
    ticket.status = Ticket.Status.PENDING
    ticket.waiting_since = timezone.now()
    if not ticket.first_response_due_at:
        ticket.first_response_due_at = timezone.now()
    ticket.next_response_due_at = None
    ticket.save(update_fields=["status", "waiting_since", "first_response_due_at", "next_response_due_at", "updated_at"])


def mark_customer_reply(ticket):
    ticket.status = Ticket.Status.OPEN
    ticket.waiting_since = None
    _, next_response, _resolution = targets_for(ticket)
    ticket.next_response_due_at = add_business_minutes(ticket.workspace, timezone.now(), next_response)
    ticket.save(update_fields=["status", "waiting_since", "next_response_due_at", "updated_at"])


def mark_resolved(ticket):
    ticket.status = Ticket.Status.RESOLVED
    ticket.resolved_at = timezone.now()
    ticket.waiting_since = None
    ticket.next_response_due_at = None
    ticket.save(update_fields=["status", "resolved_at", "waiting_since", "next_response_due_at", "updated_at"])


def sla_state(ticket):
    now = timezone.now()
    due = ticket.next_response_due_at or ticket.first_response_due_at
    if not due or ticket.status in [Ticket.Status.RESOLVED, Ticket.Status.CLOSED]:
        return "none"
    if ticket.status == Ticket.Status.PENDING:
        return "paused"
    if due <= now:
        return "breached"
    if due <= now + timezone.timedelta(hours=1):
        return "due_soon"
    return "on_track"


def targets_for(ticket):
    policy = ticket.workspace.sla_policies.filter(priority=ticket.priority).first()
    if policy:
        return policy.first_response_target_minutes, policy.next_response_target_minutes, policy.resolution_target_minutes
    return ticket.workspace.first_response_target_minutes, ticket.workspace.next_response_target_minutes, ticket.workspace.resolution_target_minutes


def add_business_minutes(workspace, start, minutes):
    calendar = getattr(workspace, "business_calendar", None)
    if not calendar:
        return start + timezone.timedelta(minutes=minutes)
    tz = ZoneInfo(calendar.timezone)
    current = start.astimezone(tz)
    remaining = minutes
    while remaining > 0:
        if _is_business_day(calendar, current):
            window_start = current.replace(hour=calendar.starts_at.hour, minute=calendar.starts_at.minute, second=0, microsecond=0)
            window_end = current.replace(hour=calendar.ends_at.hour, minute=calendar.ends_at.minute, second=0, microsecond=0)
            if current < window_start:
                current = window_start
            if window_start <= current < window_end:
                available = int((window_end - current).total_seconds() // 60)
                step = min(available, remaining)
                current += timezone.timedelta(minutes=step)
                remaining -= step
                if remaining == 0:
                    return current.astimezone(dt_timezone.utc)
        current = (current + timezone.timedelta(days=1)).replace(hour=calendar.starts_at.hour, minute=calendar.starts_at.minute, second=0, microsecond=0)
    return current.astimezone(dt_timezone.utc)


def _is_business_day(calendar, value):
    day_flags = [calendar.monday, calendar.tuesday, calendar.wednesday, calendar.thursday, calendar.friday, calendar.saturday, calendar.sunday]
    return day_flags[value.weekday()] and value.date().isoformat() not in calendar.closed_dates


def merge_ticket(source, target, user, note=""):
    if source.workspace_id != target.workspace_id:
        raise ValueError("Tickets must belong to the same workspace.")
    relation, _ = TicketRelation.objects.get_or_create(
        workspace=source.workspace,
        source=source,
        target=target,
        relation_type=TicketRelation.RelationType.MERGED,
        defaults={"created_by": user, "note": note},
    )
    source.status = Ticket.Status.CLOSED
    source.merged_into = target
    source.save(update_fields=["status", "merged_into", "updated_at"])
    return relation
