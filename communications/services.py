import email
import imaplib
import re
import uuid
from email import policy
from email.utils import getaddresses, parseaddr

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage as DjangoEmailMessage, get_connection
from django.db import IntegrityError, transaction
from django.utils import timezone
from activity.services import record_event
from crm.models import Contact
from tickets.models import Ticket, TicketComment
from tickets.services import apply_initial_sla, mark_customer_reply
from .models import EmailAttachment, EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel


TICKET_REFERENCE_RE = re.compile(r"\[Threadline:([0-9a-fA-F-]{36})\]")


def ticket_email_subject(ticket, subject=""):
    marker = f"[Threadline:{ticket.pk}]"
    clean_subject = (subject or ticket.title or "Threadline ticket").strip()
    if marker in clean_subject:
        return clean_subject
    return f"{marker} {clean_subject}"


def process_inbound_email(
    *,
    workspace,
    mailbox=None,
    message_id,
    sender,
    recipients,
    subject,
    text_body,
    provider_metadata=None,
    attachments=None,
    ticket=None,
):
    provider_metadata = provider_metadata or {}
    attachments = attachments or []
    existing = EmailMessage.objects.filter(workspace=workspace, message_id=message_id).select_related("ticket", "comment").first()
    if existing:
        action = (existing.provider_metadata or {}).get("threadline_action", "")
        target = existing.ticket if action == "ticket_created" else existing.comment or existing.ticket
        EmailIngestLog.objects.create(
            workspace=workspace,
            mailbox=mailbox,
            email_message=existing,
            message_id=message_id,
            status=EmailIngestLog.Status.DUPLICATE,
            detail="Duplicate inbound message ignored.",
            provider_metadata=provider_metadata,
        )
        return existing, target, False

    contact = Contact.objects.filter(workspace=workspace, email__iexact=sender).select_related("organization").first()
    thread_ticket = ticket or _ticket_from_metadata(workspace, provider_metadata) or _ticket_from_subject(workspace, subject)
    if thread_ticket:
        return _append_inbound_reply(
            workspace=workspace,
            mailbox=mailbox,
            ticket=thread_ticket,
            contact=contact,
            message_id=message_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            text_body=text_body,
            provider_metadata=provider_metadata,
            attachments=attachments,
        )
    return _create_inbound_ticket(
        workspace=workspace,
        mailbox=mailbox,
        contact=contact,
        message_id=message_id,
        sender=sender,
        recipients=recipients,
        subject=subject,
        text_body=text_body,
        provider_metadata=provider_metadata,
        attachments=attachments,
    )


def queue_outbound_ticket_reply(*, workspace, ticket, sender="", recipients=None, subject="", text_body="", comment=None, provider_metadata=None):
    recipients = recipients or ([ticket.contact.email] if ticket.contact and ticket.contact.email else [])
    mailbox = _outbound_mailbox(workspace)
    from_email = sender or (mailbox.address if mailbox else settings.DEFAULT_FROM_EMAIL)
    email_message = EmailMessage.objects.create(
        workspace=workspace,
        mailbox=mailbox,
        ticket=ticket,
        comment=comment,
        organization=ticket.organization,
        contact=ticket.contact,
        direction=EmailMessage.Direction.OUTBOUND,
        status=EmailMessage.Status.QUEUED,
        message_id=f"threadline-outbound-{uuid.uuid4()}@threadline.local",
        sender=from_email,
        recipients=recipients,
        subject=ticket_email_subject(ticket, subject or ticket.title),
        text_body=text_body,
        provider_metadata=provider_metadata or {},
    )
    record_email_delivery_attempt(
        workspace=workspace,
        email_message=email_message,
        status=EmailDeliveryAttempt.Status.QUEUED,
        provider=mailbox.provider if mailbox else "",
        response="Queued for SMTP delivery.",
    )
    return email_message


def outbound_mailbox_for_workspace(workspace):
    return _outbound_mailbox(workspace)


def outbound_sender_for_workspace(workspace):
    mailbox = outbound_mailbox_for_workspace(workspace)
    return mailbox.address if mailbox else settings.DEFAULT_FROM_EMAIL


def send_queued_email_message(email_message_id):
    email_message = EmailMessage.objects.select_related("workspace", "mailbox").get(pk=email_message_id)
    if email_message.direction != EmailMessage.Direction.OUTBOUND:
        return {"email_message_id": str(email_message_id), "status": "skipped", "detail": "Message is not outbound."}
    try:
        django_message = DjangoEmailMessage(
            subject=email_message.subject,
            body=email_message.text_body,
            from_email=email_message.sender,
            to=email_message.recipients,
            connection=_smtp_connection(email_message.mailbox),
        )
        sent_count = django_message.send(fail_silently=False)
        if sent_count:
            email_message.status = EmailMessage.Status.PROCESSED
            email_message.processed_at = timezone.now()
            email_message.save(update_fields=["status", "processed_at"])
            record_email_delivery_attempt(
                workspace=email_message.workspace,
                email_message=email_message,
                status=EmailDeliveryAttempt.Status.SENT,
                provider=email_message.mailbox.provider if email_message.mailbox else "",
                response="Sent via SMTP.",
            )
            return {"email_message_id": str(email_message_id), "status": "sent"}
        response = "Django email backend reported zero sent messages."
    except Exception as exc:
        response = str(exc)

    email_message.status = EmailMessage.Status.FAILED
    email_message.save(update_fields=["status"])
    record_email_delivery_attempt(
        workspace=email_message.workspace,
        email_message=email_message,
        status=EmailDeliveryAttempt.Status.FAILED,
        provider=email_message.mailbox.provider if email_message.mailbox else "",
        response=response[:2000],
    )
    return {"email_message_id": str(email_message_id), "status": "failed", "detail": response[:500]}


def poll_mailbox_channel(mailbox_id, limit=25):
    mailbox = MailboxChannel.objects.select_related("workspace").get(pk=mailbox_id)
    if not mailbox.inbound_enabled or mailbox.status != MailboxChannel.Status.READY:
        return {"mailbox_id": str(mailbox_id), "status": "disabled", "processed": 0}
    processed = 0
    last_uid = mailbox.imap_last_uid
    for inbound in _fetch_imap_messages(mailbox, limit=limit):
        email_message, _, created = process_inbound_email(
            workspace=mailbox.workspace,
            mailbox=mailbox,
            message_id=inbound["message_id"],
            sender=inbound["sender"],
            recipients=inbound["recipients"],
            subject=inbound["subject"],
            text_body=inbound["text_body"],
            provider_metadata=inbound["provider_metadata"],
            attachments=inbound["attachments"],
        )
        if created:
            processed += 1
        last_uid = inbound.get("uid") or last_uid
    if last_uid and last_uid != mailbox.imap_last_uid:
        mailbox.imap_last_uid = str(last_uid)
        mailbox.save(update_fields=["imap_last_uid", "updated_at"])
    return {"mailbox_id": str(mailbox_id), "status": "processed", "processed": processed}


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


def _create_inbound_ticket(*, workspace, mailbox, contact, message_id, sender, recipients, subject, text_body, provider_metadata, attachments):
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
            metadata = {**provider_metadata, "threadline_action": "ticket_created"}
            email_message = EmailMessage.objects.create(
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
                provider_metadata=metadata,
                processed_at=timezone.now(),
            )
            _store_email_attachments(email_message, attachments)
            EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=email_message, message_id=message_id, status=EmailIngestLog.Status.PROCESSED, detail="Inbound email created ticket.", provider_metadata=metadata)
            record_event(workspace=workspace, ticket=ticket, event_type="email.ticket_created", summary=f"Inbound email created ticket: {subject}", customer_visible=True)
            return email_message, ticket, True
    except IntegrityError:
        existing = EmailMessage.objects.get(workspace=workspace, message_id=message_id)
        EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=existing, message_id=message_id, status=EmailIngestLog.Status.DUPLICATE, detail="Duplicate inbound message ignored.", provider_metadata=provider_metadata)
        return existing, existing.ticket, False


def _append_inbound_reply(*, workspace, mailbox, ticket, contact, message_id, sender, recipients, subject, text_body, provider_metadata, attachments):
    try:
        with transaction.atomic():
            comment = TicketComment.objects.create(workspace=workspace, ticket=ticket, author=None, body=text_body, visibility=TicketComment.Visibility.PUBLIC)
            mark_customer_reply(ticket)
            metadata = {**provider_metadata, "threadline_action": "reply_added"}
            email_message = EmailMessage.objects.create(
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
                provider_metadata=metadata,
                processed_at=timezone.now(),
            )
            _store_email_attachments(email_message, attachments)
            EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=email_message, message_id=message_id, status=EmailIngestLog.Status.PROCESSED, detail="Inbound email appended reply.", provider_metadata=metadata)
            record_event(workspace=workspace, ticket=ticket, event_type="email.reply_added", summary="Inbound email added reply", customer_visible=True)
            return email_message, comment, True
    except IntegrityError:
        existing = EmailMessage.objects.get(workspace=workspace, message_id=message_id)
        EmailIngestLog.objects.create(workspace=workspace, mailbox=mailbox, email_message=existing, message_id=message_id, status=EmailIngestLog.Status.DUPLICATE, detail="Duplicate inbound reply ignored.", provider_metadata=provider_metadata)
        return existing, existing.comment, False


def _store_email_attachments(email_message, attachments):
    for attachment in attachments:
        display_name = attachment.get("filename") or "attachment"
        content = attachment.get("content") or b""
        if isinstance(content, bytes):
            content = ContentFile(content, name=display_name)
        content_type = attachment.get("content_type", "")
        size_bytes = getattr(content, "size", 0) or len(getattr(content, "getvalue", lambda: b"")())
        record = EmailAttachment(
            workspace=email_message.workspace,
            email_message=email_message,
            display_name=display_name,
            content_type=content_type,
            size_bytes=size_bytes,
            provider_metadata=attachment.get("provider_metadata") or {},
        )
        record.file.save(display_name, content, save=False)
        record.save()


def _ticket_from_subject(workspace, subject):
    match = TICKET_REFERENCE_RE.search(subject or "")
    if not match:
        return None
    try:
        ticket_id = uuid.UUID(match.group(1))
    except ValueError:
        return None
    return Ticket.objects.filter(workspace=workspace, pk=ticket_id).first()


def _ticket_from_metadata(workspace, provider_metadata):
    raw_ticket_id = (provider_metadata or {}).get("ticket_id")
    if not raw_ticket_id:
        return None
    try:
        ticket_id = uuid.UUID(str(raw_ticket_id))
    except ValueError:
        return None
    return Ticket.objects.filter(workspace=workspace, pk=ticket_id).first()


def _outbound_mailbox(workspace):
    return MailboxChannel.objects.filter(workspace=workspace, outbound_enabled=True, status=MailboxChannel.Status.READY).order_by("name").first()


def _smtp_connection(mailbox):
    if mailbox and mailbox.smtp_host:
        return get_connection(
            host=mailbox.smtp_host,
            port=mailbox.smtp_port,
            username=mailbox.smtp_username or None,
            password=mailbox.get_smtp_password() or None,
            use_tls=mailbox.smtp_use_tls,
            use_ssl=mailbox.smtp_use_ssl,
            timeout=getattr(settings, "EMAIL_TIMEOUT", None),
        )
    return get_connection()


def _fetch_imap_messages(mailbox, limit=25):
    client_class = imaplib.IMAP4_SSL if mailbox.imap_use_ssl else imaplib.IMAP4
    client = client_class(mailbox.imap_host, mailbox.imap_port)
    try:
        if mailbox.imap_username:
            client.login(mailbox.imap_username, mailbox.get_imap_password())
        client.select(mailbox.imap_folder or "INBOX")
        if mailbox.imap_last_uid and mailbox.imap_last_uid.isdigit():
            criteria = f"{int(mailbox.imap_last_uid) + 1}:*"
            status, data = client.uid("search", None, criteria)
        else:
            status, data = client.uid("search", None, "UNSEEN")
        if status != "OK" or not data:
            return []
        uids = data[0].split()[:limit]
        messages = []
        for uid in uids:
            fetch_status, fetch_data = client.uid("fetch", uid, "(RFC822)")
            if fetch_status != "OK" or not fetch_data:
                continue
            raw = next((part[1] for part in fetch_data if isinstance(part, tuple) and len(part) > 1), None)
            if not raw:
                continue
            messages.append(_parse_raw_email(raw, uid.decode("ascii", errors="ignore")))
        return messages
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass


def _parse_raw_email(raw, uid):
    parsed = email.message_from_bytes(raw, policy=policy.default)
    body_part = parsed.get_body(preferencelist=("plain", "html"))
    text_body = body_part.get_content() if body_part else ""
    attachments = []
    for part in parsed.iter_attachments():
        filename = part.get_filename() or "attachment"
        attachments.append(
            {
                "filename": filename,
                "content": ContentFile(part.get_content(), name=filename),
                "content_type": part.get_content_type(),
                "provider_metadata": {"content_id": part.get("Content-ID", "")},
            }
        )
    return {
        "uid": uid,
        "message_id": parsed.get("Message-ID") or f"imap-{uid}",
        "sender": parseaddr(parsed.get("From", ""))[1] or parsed.get("From", ""),
        "recipients": [address for _, address in getaddresses([parsed.get("To", "") or ""]) if address],
        "subject": parsed.get("Subject", ""),
        "text_body": text_body,
        "attachments": attachments,
        "provider_metadata": {"imap_uid": uid, "in_reply_to": parsed.get("In-Reply-To", ""), "references": parsed.get("References", "")},
    }
