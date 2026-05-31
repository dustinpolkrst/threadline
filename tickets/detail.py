from django.db.models import Q, Sum

from ai.views import ai_panel_context
from communications.models import EmailMessage
from communications.services import outbound_mailbox_for_workspace, outbound_sender_for_workspace, ticket_email_subject
from time_tracking.forms import TimeEntryForm, TimerStartForm, TimerStopForm
from time_tracking.models import ActiveTimer

from .email import ticket_reply_recipient
from .forms import CommentForm, TicketAttachmentForm, TicketEmailReplyForm, TicketRelationForm
from .models import Ticket, TicketRelation
from .services import sla_state


def build_ticket_detail_context(request, workspace, ticket):
    time_entries = ticket.time_entries.filter(workspace=workspace).select_related("user")
    relations = TicketRelation.objects.filter(workspace=workspace).filter(Q(source=ticket) | Q(target=ticket))
    outbound_mailbox = outbound_mailbox_for_workspace(workspace)
    email_reply_subject_preview = ticket_email_subject(ticket, f"Re: {ticket.title}")
    ticket.sla_state = sla_state(ticket)
    context = {
        "ticket": ticket,
        "comments": ticket.comments.filter(workspace=workspace).select_related("author"),
        "comment_form": CommentForm(),
        "email_reply_form": TicketEmailReplyForm(initial={"subject": email_reply_subject_preview}),
        "email_reply_recipient": ticket_reply_recipient(ticket),
        "email_reply_sender": outbound_sender_for_workspace(workspace),
        "email_reply_mailbox": outbound_mailbox,
        "email_reply_subject_preview": email_reply_subject_preview,
        "recent_email_messages": _recent_outbound_email_messages(workspace, ticket),
        "time_form": TimeEntryForm(),
        "timer_start_form": TimerStartForm(),
        "timer_stop_form": TimerStopForm(),
        "active_timer": ActiveTimer.objects.filter(workspace=workspace, user=request.user).select_related("ticket").first(),
        "time_entries": time_entries,
        "time_total": time_entries.aggregate(total=Sum("duration_minutes"))["total"] or 0,
        "activity": ticket.activity_events.filter(workspace=workspace).select_related("actor"),
        "attachments": ticket.attachments.filter(workspace=workspace).select_related("uploaded_by"),
        "attachment_form": TicketAttachmentForm(),
        "relation_form": relation_form(workspace, ticket),
        "relations": relations.select_related("source", "target", "created_by"),
    }
    context.update(ai_panel_context(ticket, workspace))
    return context


def _recent_outbound_email_messages(workspace, ticket):
    email_messages = (
        EmailMessage.objects.filter(
            workspace=workspace,
            ticket=ticket,
            direction=EmailMessage.Direction.OUTBOUND,
        )
        .select_related("mailbox", "comment")
        .prefetch_related("delivery_attempts")[:5]
    )
    return [{"message": email_message, "latest_attempt": next(iter(email_message.delivery_attempts.all()), None)} for email_message in email_messages]


def relation_form(workspace, ticket, data=None):
    form = TicketRelationForm(data)
    form.fields["target"].queryset = Ticket.objects.filter(workspace=workspace).exclude(pk=ticket.pk)
    return form
