import uuid
from datetime import time
from secrets import token_urlsafe

from django.conf import settings
from django.utils import timezone
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    first_response_target_minutes = models.PositiveIntegerField(default=240)
    next_response_target_minutes = models.PositiveIntegerField(default=480)
    resolution_target_minutes = models.PositiveIntegerField(default=4320)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkspaceMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agent"
        VIEWER = "viewer", "Viewer"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("workspace", "user")]
        indexes = [models.Index(fields=["workspace", "user"]), models.Index(fields=["user", "role"])]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.role})"


class ApplicationStorageSettings(models.Model):
    class Backend(models.TextChoices):
        LOCAL = "local", "Local filesystem"
        S3 = "s3", "S3-compatible"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="storage_settings")
    backend = models.CharField(max_length=20, choices=Backend.choices, default=Backend.LOCAL)
    bucket_name = models.CharField(max_length=255, blank=True)
    endpoint_url = models.URLField(blank=True)
    region_name = models.CharField(max_length=80, blank=True)
    access_key_id = models.CharField(max_length=255, blank=True)
    secret_access_key = models.CharField(max_length=255, blank=True)
    custom_domain = models.CharField(max_length=255, blank=True)
    addressing_style = models.CharField(max_length=20, default="auto")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "application storage settings"

    @property
    def is_s3_enabled(self):
        return self.backend == self.Backend.S3 and bool(self.bucket_name)

    def __str__(self):
        return f"{self.workspace} storage: {self.get_backend_display()}"


class SLAPolicy(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sla_policies")
    priority = models.CharField(max_length=20, choices=Priority.choices)
    first_response_target_minutes = models.PositiveIntegerField(default=240)
    next_response_target_minutes = models.PositiveIntegerField(default=480)
    resolution_target_minutes = models.PositiveIntegerField(default=4320)

    class Meta:
        unique_together = [("workspace", "priority")]
        indexes = [models.Index(fields=["workspace", "priority"])]


class BusinessHoursCalendar(models.Model):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="business_calendar")
    timezone = models.CharField(max_length=80, default="UTC")
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    starts_at = models.TimeField(default=time(9, 0))
    ends_at = models.TimeField(default=time(17, 0))
    closed_dates = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.workspace} business hours"


class Invitation(models.Model):
    class InviteType(models.TextChoices):
        INTERNAL = "internal", "Internal user"
        CUSTOMER = "customer", "Customer user"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    invite_type = models.CharField(max_length=20, choices=InviteType.choices)
    role = models.CharField(max_length=20, choices=WorkspaceMembership.Role.choices, blank=True)
    organization = models.ForeignKey("crm.Organization", on_delete=models.CASCADE, null=True, blank=True, related_name="invitations")
    contact = models.ForeignKey("crm.Contact", on_delete=models.CASCADE, null=True, blank=True, related_name="invitations")
    token = models.CharField(max_length=160, unique=True, default=token_urlsafe)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_workspace_invitations")
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_workspace_invitations")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "invite_type"]), models.Index(fields=["token"]), models.Index(fields=["workspace", "email"])]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_accepted(self):
        return bool(self.accepted_at)


def first_workspace_for(user):
    if not user.is_authenticated:
        return None
    membership = user.workspace_memberships.select_related("workspace").first()
    return membership.workspace if membership else None

# Create your models here.
