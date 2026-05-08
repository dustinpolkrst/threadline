import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tickets", "0004_savedticketfilter_ticketrelation_and_more"),
        ("workspaces", "0004_applicationstoragesettings"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIProviderSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("openrouter", "OpenRouter")], default="openrouter", max_length=30)),
                ("enabled", models.BooleanField(default=False)),
                ("api_key", models.CharField(blank=True, max_length=500)),
                ("model", models.CharField(default="openrouter/auto", max_length=160)),
                ("zdr_only", models.BooleanField(default=True)),
                ("auto_triage_enabled", models.BooleanField(default=False)),
                ("max_historical_tickets", models.PositiveSmallIntegerField(default=5)),
                ("last_test_status", models.CharField(blank=True, max_length=20)),
                ("last_test_message", models.CharField(blank=True, max_length=500)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ai_settings", to="workspaces.workspace")),
            ],
            options={"verbose_name_plural": "AI provider settings"},
        ),
        migrations.CreateModel(
            name="TicketAIAnalysis",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("applied", "Applied")], default="queued", max_length=20)),
                ("mode", models.CharField(choices=[("draft", "Draft only"), ("auto_triage", "Auto-triage")], default="draft", max_length=20)),
                ("summary", models.TextField(blank=True)),
                ("suggested_priority", models.CharField(blank=True, max_length=20)),
                ("suggested_tags", models.JSONField(blank=True, default=list)),
                ("suggested_assignee_reason", models.TextField(blank=True)),
                ("solution_draft", models.TextField(blank=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("context_refs", models.JSONField(blank=True, default=list)),
                ("risks", models.JSONField(blank=True, default=list)),
                ("raw_model", models.CharField(blank=True, max_length=160)),
                ("prompt_tokens", models.PositiveIntegerField(default=0)),
                ("completion_tokens", models.PositiveIntegerField(default=0)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("applied_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="applied_ai_analyses", to=settings.AUTH_USER_MODEL)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_ai_analyses", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_analyses", to="tickets.ticket")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticket_ai_analyses", to="workspaces.workspace")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["workspace", "ticket", "created_at"], name="ai_ticketai_workspa_7db50d_idx"),
                    models.Index(fields=["workspace", "status"], name="ai_ticketai_workspa_de143a_idx"),
                ],
            },
        ),
    ]
