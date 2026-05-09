import uuid

from django.conf import settings
from django.db import models
from crm.models import Contact, Organization
from tickets.models import Ticket
from workspaces.models import Workspace


class ActivityEvent(models.Model):
    class Visibility(models.TextChoices):
        INTERNAL = "internal", "Internal"
        CUSTOMER = "customer", "Customer visible"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="activity_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_events")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_events")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_events")
    event_type = models.CharField(max_length=80)
    summary = models.CharField(max_length=255)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.INTERNAL)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["workspace", "ticket", "visibility"]),
            models.Index(fields=["workspace", "organization"]),
            models.Index(fields=["workspace", "contact"]),
            models.Index(fields=["workspace", "event_type"]),
            models.Index(fields=["workspace", "actor"]),
        ]

    def __str__(self):
        return self.summary
