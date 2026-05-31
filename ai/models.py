import uuid

from django.conf import settings
from django.db import models

from crm.models import Contact, Organization
from tickets.models import Ticket
from time_tracking.models import TimeEntry
from workspaces.models import Workspace
from .crypto import decrypt_secret, encrypt_secret, is_encrypted


class AIProviderSettings(models.Model):
    class Provider(models.TextChoices):
        OPENROUTER = "openrouter", "OpenRouter"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="ai_settings")
    provider = models.CharField(max_length=30, choices=Provider.choices, default=Provider.OPENROUTER)
    enabled = models.BooleanField(default=False)
    api_key = models.CharField(max_length=500, blank=True)
    encrypted_api_key = models.TextField(blank=True)
    model = models.CharField(max_length=160, default="openrouter/auto")
    zdr_only = models.BooleanField(default=True)
    auto_triage_enabled = models.BooleanField(default=False)
    reply_composer_enabled = models.BooleanField(default=True)
    solution_memory_enabled = models.BooleanField(default=True)
    ticket_drafts_enabled = models.BooleanField(default=True)
    crm_insights_enabled = models.BooleanField(default=True)
    time_suggestions_enabled = models.BooleanField(default=True)
    queue_intelligence_enabled = models.BooleanField(default=True)
    digest_enabled = models.BooleanField(default=False)
    max_historical_tickets = models.PositiveSmallIntegerField(default=5)
    monthly_token_cap = models.PositiveIntegerField(default=0)
    monthly_run_cap = models.PositiveIntegerField(default=0)
    generation_retention_days = models.PositiveIntegerField(default=90)
    last_test_status = models.CharField(max_length=20, blank=True)
    last_test_message = models.CharField(max_length=500, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "AI provider settings"

    @property
    def has_api_key(self):
        return bool(self.encrypted_api_key or self.api_key)

    def get_api_key(self):
        return decrypt_secret(self.encrypted_api_key or self.api_key)

    def set_api_key(self, value):
        self.encrypted_api_key = encrypt_secret(value)
        self.api_key = ""

    def save(self, *args, **kwargs):
        if self.api_key and not self.encrypted_api_key:
            self.set_api_key(self.api_key)
        elif self.encrypted_api_key and not is_encrypted(self.encrypted_api_key):
            self.encrypted_api_key = encrypt_secret(self.encrypted_api_key)
        super().save(*args, **kwargs)

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
    customer_sentiment = models.CharField(max_length=40, blank=True)
    urgency_reason = models.TextField(blank=True)
    next_best_action = models.TextField(blank=True)
    similar_tickets = models.JSONField(default=list, blank=True)
    suggested_priority = models.CharField(max_length=20, blank=True)
    suggested_status = models.CharField(max_length=20, blank=True)
    suggested_tags = models.JSONField(default=list, blank=True)
    suggested_assignee_reason = models.TextField(blank=True)
    solution_draft = models.TextField(blank=True)
    customer_reply_draft = models.TextField(blank=True)
    internal_note_draft = models.TextField(blank=True)
    root_cause_notes = models.TextField(blank=True)
    missing_info = models.JSONField(default=list, blank=True)
    escalation_risk = models.CharField(max_length=20, blank=True)
    next_actions = models.JSONField(default=list, blank=True)
    feedback = models.CharField(max_length=40, blank=True)
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


class AIRun(models.Model):
    class Workflow(models.TextChoices):
        TICKET_WORKBENCH = "ticket_workbench", "Ticket workbench"
        REPLY_COMPOSER = "reply_composer", "Reply composer"
        CRM_INSIGHT = "crm_insight", "CRM insight"
        TIME_SUGGESTION = "time_suggestion", "Time suggestion"
        WORKSPACE_DIGEST = "workspace_digest", "Workspace digest"
        SOLUTION_MEMORY = "solution_memory", "Solution memory"
        QUEUE_INTELLIGENCE = "queue_intelligence", "Queue intelligence"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_runs")
    workflow = models.CharField(max_length=40, choices=Workflow.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    subject_type = models.CharField(max_length=40, blank=True)
    subject_id = models.UUIDField(null=True, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_runs")
    output = models.JSONField(default=dict, blank=True)
    context_refs = models.JSONField(default=list, blank=True)
    selected_actions = models.JSONField(default=list, blank=True)
    rejected_actions = models.JSONField(default=list, blank=True)
    feedback = models.CharField(max_length=40, blank=True)
    raw_model = models.CharField(max_length=160, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    provider_generation_id = models.CharField(max_length=120, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    privacy_mode = models.CharField(max_length=20, default="zdr")
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "workflow", "created_at"]),
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "subject_type", "subject_id"]),
        ]

    def __str__(self):
        return f"{self.get_workflow_display()} ({self.status})"


class AISuggestedAction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_suggested_actions")
    run = models.ForeignKey(AIRun, on_delete=models.CASCADE, related_name="suggested_actions", null=True, blank=True)
    ticket_analysis = models.ForeignKey(TicketAIAnalysis, on_delete=models.CASCADE, related_name="suggested_actions", null=True, blank=True)
    action_type = models.CharField(max_length=40)
    title = models.CharField(max_length=180)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="applied_ai_actions")
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "action_type"])]


class TicketReplyDraft(models.Model):
    class Audience(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        INTERNAL = "internal", "Internal"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ticket_reply_drafts")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_reply_drafts")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_reply_drafts")
    analysis = models.ForeignKey(TicketAIAnalysis, on_delete=models.SET_NULL, null=True, blank=True, related_name="reply_drafts")
    audience = models.CharField(max_length=20, choices=Audience.choices)
    body = models.TextField()
    prompt = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "ticket", "status"])]


class CRMInsight(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="crm_insights")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="ai_insights")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True, blank=True, related_name="ai_insights")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_insights")
    summary = models.TextField()
    support_tone = models.CharField(max_length=80, blank=True)
    recommended_next_touch = models.TextField(blank=True)
    hygiene_suggestions = models.JSONField(default=list, blank=True)
    recurring_issues = models.JSONField(default=list, blank=True)
    product_areas = models.JSONField(default=list, blank=True)
    risks = models.JSONField(default=list, blank=True)
    suggestions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "organization", "created_at"]), models.Index(fields=["workspace", "contact", "created_at"])]


class TimeEntrySuggestion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="time_entry_suggestions")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_time_suggestions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_time_suggestions")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="time_suggestions")
    suggested_minutes = models.PositiveIntegerField(default=15)
    billable = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_time_entry = models.ForeignKey(TimeEntry, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "ticket", "status"]), models.Index(fields=["workspace", "user", "status"])]


class WorkspaceDigest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_digests")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="workspace_digests")
    period_start = models.DateField()
    period_end = models.DateField()
    summary = models.TextField()
    themes = models.JSONField(default=list, blank=True)
    accounts_at_risk = models.JSONField(default=list, blank=True)
    time_insights = models.JSONField(default=list, blank=True)
    suggestions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]
        indexes = [models.Index(fields=["workspace", "period_end"])]


class SolutionSnippet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="solution_snippets")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="solution_snippets")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="solution_snippets")
    title = models.CharField(max_length=180)
    body = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "approved"])]


class QueueIntelligenceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_queue_snapshots")
    run = models.ForeignKey(AIRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="queue_snapshots")
    likely_urgent = models.JSONField(default=list, blank=True)
    stale_pending = models.JSONField(default=list, blank=True)
    missing_customer_info = models.JSONField(default=list, blank=True)
    probable_duplicates = models.JSONField(default=list, blank=True)
    sla_risks = models.JSONField(default=list, blank=True)
    high_effort_accounts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "created_at"])]
