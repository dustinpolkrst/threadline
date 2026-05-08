import uuid

from django.conf import settings
from django.db import models
from crm.models import Contact, Organization
from tickets.models import Ticket
from workspaces.models import Workspace


class TimeEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_entries")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name="time_entries")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="time_entries")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="time_entries")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField()
    billable = models.BooleanField(default=False)
    customer_visible = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["workspace", "user", "started_at"]),
            models.Index(fields=["workspace", "ticket"]),
            models.Index(fields=["workspace", "organization"]),
            models.Index(fields=["workspace", "contact"]),
            models.Index(fields=["workspace", "customer_visible"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.duration_minutes}m"


class ActiveTimer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="active_timers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="active_timers")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="active_timers")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="active_timers")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="active_timers")
    started_at = models.DateTimeField()
    billable = models.BooleanField(default=True)
    customer_visible = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "user"], name="one_active_timer_per_workspace_user")]
        indexes = [
            models.Index(fields=["workspace", "user"]),
            models.Index(fields=["workspace", "ticket"]),
        ]

    def __str__(self):
        return f"{self.user} timer on {self.ticket}"
