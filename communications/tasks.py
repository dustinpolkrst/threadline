from celery import shared_task
from .models import EmailDeliveryAttempt, EmailMessage
from .services import poll_mailbox_channel, record_email_delivery_attempt, send_queued_email_message


@shared_task
def poll_mailbox_channel_stub(mailbox_id):
    return {"mailbox_id": str(mailbox_id), "status": "stubbed", "detail": "Inbound email provider is not configured."}


@shared_task
def send_email_message_stub(email_message_id):
    email = EmailMessage.objects.get(pk=email_message_id)
    record_email_delivery_attempt(
        workspace=email.workspace,
        email_message=email,
        status=EmailDeliveryAttempt.Status.STUBBED,
        response="Outbound email provider is not configured.",
    )
    return {"email_message_id": str(email_message_id), "status": "stubbed"}


@shared_task
def poll_mailbox_channel_with_provider(mailbox_id, limit=25):
    return poll_mailbox_channel(mailbox_id, limit=limit)


@shared_task
def send_email_message(email_message_id):
    return send_queued_email_message(email_message_id)
