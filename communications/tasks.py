from celery import shared_task
from .models import EmailDeliveryAttempt, EmailMessage
from .services import record_email_delivery_attempt


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
