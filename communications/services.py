from django.db import IntegrityError, transaction
from django.utils import timezone
from activity.services import record_event
from crm.models import Contact
from tickets.models import Ticket, TicketComment
from tickets.services import apply_initial_sla, mark_customer_reply
from .models import EmailDeliveryAttempt, EmailIngestLog, EmailMessage


def create_ticket_from_inbound_email_stub(*, workspace, mailbox=None, message_id, sender, recipients, subject, text_body, provider_metadata=None):
    provider_metadata = provider_metadata or {}
    contact = Contact.objects.filter(workspace=workspace, email__iexact=sender).select_related("organization").first()
    try:
        with transaction.atomic():
            ticket = Ticket.objects.create(
                workspace=workspace,
                organization=contact.organization if contact else None,
                contact=contact,
                title=subject or "Inbound email",
                description=text_body,
                source=Ticket.Source.EMAIL,
                status=Ticket.Status.OPEN,
            )
            apply_initial_sla(ticket)
            ticket.save(update_fields=["first_response_due_at", "next_response_due_at", "updated_at"])
            comment = TicketComment.objects.create(
                workspace=workspace,
                ticket=ticket,
                author=None,
                body=text_body,
                visibility=TicketComment.Visibility.PUBLIC,
            )
            email = EmailMessage.objects.create(
                workspace=workspace,
                mailbox=mailbox,
                ticket=ticket,
                comment=comment,
                organization=ticket.organization,
                contact=ticket.contact,
                direction=EmailMessage.Direction.INBOUND,
                status=EmailMessage.Status.PROCESSED,
                message_id=message_id,
                sender=sender,
                recipients=recipients,
                subject=subject,
                text_body=text_body,
                provider_metadata=provider_metadata,
                processed_at=timezone.now(),
            )
            EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=email, message_id=message_id, status=EmailIngestLog.Status.PROCESSED, detail="Stub inbound email created ticket.", provider_metadata=provider_metadata)
            record_event(workspace=workspace, ticket=ticket, event_type="email.ticket_created", summary=f"Stub inbound email created ticket: {subject}", customer_visible=True)
            return email, ticket, True
    except IntegrityError:
        existing = EmailMessage.objects.get(workspace=workspace, message_id=message_id)
        EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=existing, message_id=message_id, status=EmailIngestLog.Status.DUPLICATE, detail="Duplicate stub inbound message ignored.", provider_metadata=provider_metadata)
        return existing, existing.ticket, False


def append_reply_from_inbound_email_stub(*, workspace, ticket, mailbox=None, message_id, sender, recipients, subject, text_body, provider_metadata=None):
    provider_metadata = provider_metadata or {}
    contact = Contact.objects.filter(workspace=workspace, email__iexact=sender).select_related("organization").first()
    try:
        with transaction.atomic():
            comment = TicketComment.objects.create(workspace=workspace, ticket=ticket, author=None, body=text_body, visibility=TicketComment.Visibility.PUBLIC)
            mark_customer_reply(ticket)
            email = EmailMessage.objects.create(
                workspace=workspace,
                mailbox=mailbox,
                ticket=ticket,
                comment=comment,
                organization=ticket.organization,
                contact=contact or ticket.contact,
                direction=EmailMessage.Direction.INBOUND,
                status=EmailMessage.Status.PROCESSED,
                message_id=message_id,
                sender=sender,
                recipients=recipients,
                subject=subject,
                text_body=text_body,
                provider_metadata=provider_metadata,
                processed_at=timezone.now(),
            )
            EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=email, message_id=message_id, status=EmailIngestLog.Status.PROCESSED, detail="Stub inbound email appended reply.", provider_metadata=provider_metadata)
            record_event(workspace=workspace, ticket=ticket, event_type="email.reply_added", summary="Stub inbound email added reply", customer_visible=True)
            return email, comment, True
    except IntegrityError:
        existing = EmailMessage.objects.get(workspace=workspace, message_id=message_id)
        EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=existing, message_id=message_id, status=EmailIngestLog.Status.DUPLICATE, detail="Duplicate stub inbound reply ignored.", provider_metadata=provider_metadata)
        return existing, existing.comment, False


def queue_outbound_ticket_reply_stub(*, workspace, ticket, comment=None, sender, recipients, subject, text_body, provider_metadata=None):
    email = EmailMessage.objects.create(
        workspace=workspace,
        ticket=ticket,
        comment=comment,
        organization=ticket.organization,
        contact=ticket.contact,
        direction=EmailMessage.Direction.OUTBOUND,
        status=EmailMessage.Status.STUBBED,
        message_id=f"stub-outbound-{timezone.now().timestamp()}-{ticket.pk}",
        sender=sender,
        recipients=recipients,
        subject=subject,
        text_body=text_body,
        provider_metadata=provider_metadata or {},
    )
    record_email_delivery_attempt(workspace=workspace, email_message=email, status=EmailDeliveryAttempt.Status.STUBBED, response="Outbound email provider is not configured.")
    return email


def record_email_delivery_attempt(*, workspace, email_message, status, provider="", response=""):
    return EmailDeliveryAttempt.objects.create(workspace=workspace, email_message=email_message, status=status, provider=provider, response=response)
