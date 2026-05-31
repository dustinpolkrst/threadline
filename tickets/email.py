from dataclasses import dataclass

from django.db import transaction

from activity.services import record_event
from communications.models import EmailMessage
from communications.services import queue_outbound_ticket_reply, send_queued_email_message
from search.services import index_comment

from .models import TicketComment
from .services import mark_agent_reply


class TicketEmailReplyError(ValueError):
    pass


@dataclass(frozen=True)
class TicketEmailReplyResult:
    comment: TicketComment
    email_message: EmailMessage
    send_result: dict

    @property
    def sent(self):
        return self.send_result.get("status") == "sent"

    @property
    def failure_detail(self):
        return self.send_result.get("detail", "")


def ticket_reply_recipient(ticket):
    contact_email = getattr(getattr(ticket, "contact", None), "email", "")
    if contact_email:
        return contact_email
    requester_email = getattr(getattr(ticket, "requester", None), "email", "")
    return requester_email or ""


def send_ticket_email_reply(*, workspace, ticket, author, subject="", body=""):
    body = (body or "").strip()
    if not body:
        raise TicketEmailReplyError("Reply body is required.")

    recipient = ticket_reply_recipient(ticket)
    if not recipient:
        raise TicketEmailReplyError("No customer email address is available for this ticket.")

    with transaction.atomic():
        comment = TicketComment.objects.create(
            workspace=workspace,
            ticket=ticket,
            author=author,
            body=body,
            visibility=TicketComment.Visibility.PUBLIC,
        )
        email_message = queue_outbound_ticket_reply(
            workspace=workspace,
            ticket=ticket,
            recipients=[recipient],
            subject=(subject or "").strip() or ticket.title,
            text_body=body,
            comment=comment,
            provider_metadata={"threadline_action": "agent_email_reply", "actor_id": str(author.pk)},
        )
        index_comment(comment)
        mark_agent_reply(ticket)

    send_result = send_queued_email_message(email_message.pk)
    email_message.refresh_from_db()
    if send_result.get("status") == "sent":
        record_event(
            workspace=workspace,
            actor=author,
            ticket=ticket,
            event_type="email.reply_sent",
            summary=f"Customer email sent to {recipient}",
            customer_visible=False,
        )
    else:
        detail = (send_result.get("detail") or "SMTP delivery failed.")[:160]
        record_event(
            workspace=workspace,
            actor=author,
            ticket=ticket,
            event_type="email.reply_failed",
            summary=f"Customer email failed to send to {recipient}: {detail}"[:255],
            customer_visible=False,
        )
    return TicketEmailReplyResult(comment=comment, email_message=email_message, send_result=send_result)
