import uuid

from django.db import models
from crm.models import Contact, Organization
from tickets.models import Ticket, TicketComment
from workspaces.models import Workspace
from ai.crypto import decrypt_secret, encrypt_secret, is_encrypted


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
    inbound_enabled = models.BooleanField(default=False)
    outbound_enabled = models.BooleanField(default=False)
    imap_host = models.CharField(max_length=255, blank=True)
    imap_port = models.PositiveIntegerField(default=993)
    imap_use_ssl = models.BooleanField(default=True)
    imap_username = models.CharField(max_length=255, blank=True)
    encrypted_imap_password = models.TextField(blank=True)
    imap_folder = models.CharField(max_length=120, default="INBOX")
    imap_last_uid = models.CharField(max_length=80, blank=True)
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_username = models.CharField(max_length=255, blank=True)
    encrypted_smtp_password = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("workspace", "address")]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "address"])]

    def __str__(self):
        return f"{self.name} <{self.address}>"

    @property
    def has_imap_password(self):
        return bool(self.encrypted_imap_password)

    @property
    def has_smtp_password(self):
        return bool(self.encrypted_smtp_password)

    def get_imap_password(self):
        return decrypt_secret(self.encrypted_imap_password)

    def get_smtp_password(self):
        return decrypt_secret(self.encrypted_smtp_password)

    def set_imap_password(self, value):
        self.encrypted_imap_password = encrypt_secret(value)

    def set_smtp_password(self, value):
        self.encrypted_smtp_password = encrypt_secret(value)

    def save(self, *args, **kwargs):
        if self.encrypted_imap_password and not is_encrypted(self.encrypted_imap_password):
            self.encrypted_imap_password = encrypt_secret(self.encrypted_imap_password)
        if self.encrypted_smtp_password and not is_encrypted(self.encrypted_smtp_password):
            self.encrypted_smtp_password = encrypt_secret(self.encrypted_smtp_password)
        super().save(*args, **kwargs)


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
