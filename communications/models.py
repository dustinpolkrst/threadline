import uuid

from django.db import models
from crm.models import Contact, Organization
from tickets.models import Ticket, TicketComment
from workspaces.models import Workspace


class MailboxChannel(models.Model):
    class Status(models.TextChoices):
        DISABLED = "disabled", "Disabled"
        STUBBED = "stubbed", "Stubbed"
        READY = "ready", "Ready for provider"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="mailbox_channels")
    name = models.CharField(max_length=160)
    address = models.EmailField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STUBBED)
    provider = models.CharField(max_length=80, blank=True)
    provider_config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("workspace", "address")]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "address"])]

    def __str__(self):
        return f"{self.name} <{self.address}>"


class EmailMessage(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class Status(models.TextChoices):
        STUBBED = "stubbed", "Stubbed"
        QUEUED = "queued", "Queued"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="email_messages")
    mailbox = models.ForeignKey(MailboxChannel, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages")
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_messages")
    comment = models.ForeignKey(TicketComment, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_messages")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_messages")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_messages")
    direction = models.CharField(max_length=20, choices=Direction.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STUBBED)
    message_id = models.CharField(max_length=255)
    sender = models.EmailField()
    recipients = models.JSONField(default=list)
    subject = models.CharField(max_length=255)
    text_body = models.TextField(blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("workspace", "message_id")]
        indexes = [
            models.Index(fields=["workspace", "direction", "status"]),
            models.Index(fields=["workspace", "ticket"]),
            models.Index(fields=["workspace", "message_id"]),
            models.Index(fields=["workspace", "processed_at"]),
        ]

    def __str__(self):
        return f"{self.direction}: {self.subject}"


class EmailDeliveryAttempt(models.Model):
    class Status(models.TextChoices):
        STUBBED = "stubbed", "Stubbed"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="email_delivery_attempts")
    email_message = models.ForeignKey(EmailMessage, on_delete=models.CASCADE, related_name="delivery_attempts")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STUBBED)
    provider = models.CharField(max_length=80, blank=True)
    response = models.TextField(blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "attempted_at"])]


class EmailIngestLog(models.Model):
    class Status(models.TextChoices):
        STUBBED = "stubbed", "Stubbed"
        PROCESSED = "processed", "Processed"
        DUPLICATE = "duplicate", "Duplicate"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="email_ingest_logs")
    mailbox = models.ForeignKey(MailboxChannel, on_delete=models.SET_NULL, null=True, blank=True, related_name="ingest_logs")
    email_message = models.ForeignKey(EmailMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name="ingest_logs")
    message_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STUBBED)
    detail = models.TextField(blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "message_id"])]


class EmailAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="email_attachments")
    email_message = models.ForeignKey(EmailMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="email-attachments/")
    display_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    provider_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "email_message"]), models.Index(fields=["workspace", "created_at"])]

    def __str__(self):
        return self.display_name

# Create your models here.
