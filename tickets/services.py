from django.utils import timezone
from .models import Ticket


OPEN_STATUSES = [Ticket.Status.NEW, Ticket.Status.OPEN, Ticket.Status.PENDING]


def apply_initial_sla(ticket):
    now = timezone.now()
    ticket.first_response_due_at = now + timezone.timedelta(minutes=ticket.workspace.first_response_target_minutes)
    ticket.next_response_due_at = now + timezone.timedelta(minutes=ticket.workspace.next_response_target_minutes)
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
    ticket.next_response_due_at = timezone.now() + timezone.timedelta(minutes=ticket.workspace.next_response_target_minutes)
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
    if due <= now:
        return "breached"
    if due <= now + timezone.timedelta(hours=1):
        return "due_soon"
    return "on_track"
