import uuid

from django.conf import settings
from django.db import models

from tickets.models import Ticket
from workspaces.models import Workspace


class AIProviderSettings(models.Model):
    class Provider(models.TextChoices):
        OPENROUTER = "openrouter", "OpenRouter"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="ai_settings")
    provider = models.CharField(max_length=30, choices=Provider.choices, default=Provider.OPENROUTER)
    enabled = models.BooleanField(default=False)
    api_key = models.CharField(max_length=500, blank=True)
    model = models.CharField(max_length=160, default="openrouter/auto")
    zdr_only = models.BooleanField(default=True)
    auto_triage_enabled = models.BooleanField(default=False)
    max_historical_tickets = models.PositiveSmallIntegerField(default=5)
    last_test_status = models.CharField(max_length=20, blank=True)
    last_test_message = models.CharField(max_length=500, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "AI provider settings"

    @property
    def has_api_key(self):
        return bool(self.api_key)

    def __str__(self):
        return f"{self.workspace} AI: {self.get_provider_display()}"


class TicketAIAnalysis(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        APPLIED = "applied", "Applied"

    class Mode(models.TextChoices):
        DRAFT = "draft", "Draft only"
        AUTO_TRIAGE = "auto_triage", "Auto-triage"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ticket_ai_analyses")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_analyses")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_ai_analyses")
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="applied_ai_analyses")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.DRAFT)
    summary = models.TextField(blank=True)
    suggested_priority = models.CharField(max_length=20, blank=True)
    suggested_tags = models.JSONField(default=list, blank=True)
    suggested_assignee_reason = models.TextField(blank=True)
    solution_draft = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    context_refs = models.JSONField(default=list, blank=True)
    risks = models.JSONField(default=list, blank=True)
    raw_model = models.CharField(max_length=160, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "ticket", "created_at"], name="ai_ticketai_workspa_7db50d_idx"),
            models.Index(fields=["workspace", "status"], name="ai_ticketai_workspa_de143a_idx"),
        ]

    def __str__(self):
        return f"{self.ticket} AI analysis ({self.status})"
