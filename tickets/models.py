import uuid

from django.conf import settings
from django.db import models
from crm.models import Contact, Organization
from workspaces.models import Workspace


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Source(models.TextChoices):
        INTERNAL = "internal", "Internal"
        PORTAL = "portal", "Portal"
        EMAIL = "email", "Email"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tickets")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_tickets")
    tags = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.INTERNAL)
    due_date = models.DateField(null=True, blank=True)
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    next_response_due_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True)
    merged_into = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="merged_sources")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "assignee"]),
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["workspace", "organization"]),
            models.Index(fields=["workspace", "contact"]),
            models.Index(fields=["workspace", "first_response_due_at"]),
            models.Index(fields=["workspace", "next_response_due_at"]),
            models.Index(fields=["workspace", "waiting_since"]),
        ]

    def __str__(self):
        return self.title


class TicketComment(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        INTERNAL = "internal", "Internal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ticket_comments")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_comments")
    body = models.TextField()
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.INTERNAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["workspace", "ticket", "visibility"]),
            models.Index(fields=["workspace", "created_at"]),
        ]

    def __str__(self):
        return f"{self.ticket}: {self.visibility} comment"


class TicketAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ticket_attachments")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    comment = models.ForeignKey(TicketComment, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    file = models.FileField(upload_to="ticket-attachments/")
    display_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    customer_visible = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "ticket", "customer_visible"]), models.Index(fields=["workspace", "created_at"])]

    def __str__(self):
        return self.display_name or self.file.name


class TicketRelation(models.Model):
    class RelationType(models.TextChoices):
        RELATED = "related", "Related"
        DUPLICATE = "duplicate", "Duplicate"
        MERGED = "merged", "Merged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ticket_relations")
    source = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="outgoing_relations")
    target = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="incoming_relations")
    relation_type = models.CharField(max_length=20, choices=RelationType.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = [("workspace", "source", "target", "relation_type")]
        indexes = [models.Index(fields=["workspace", "relation_type"]), models.Index(fields=["workspace", "source"]), models.Index(fields=["workspace", "target"])]


class SavedTicketFilter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="saved_ticket_filters")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_ticket_filters")
    name = models.CharField(max_length=120)
    query = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("workspace", "user", "name")]
        indexes = [models.Index(fields=["workspace", "user"]), models.Index(fields=["workspace", "is_default"])]

# Create your models here.
