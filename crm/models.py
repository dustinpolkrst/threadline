import uuid

from django.db import models
from workspaces.models import Workspace


class Organization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PROSPECT = "prospect", "Prospect"
        AT_RISK = "at_risk", "At risk"
        INACTIVE = "inactive", "Inactive"

    class Tier(models.TextChoices):
        STANDARD = "standard", "Standard"
        PRIORITY = "priority", "Priority"
        ENTERPRISE = "enterprise", "Enterprise"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="organizations")
    name = models.CharField(max_length=220)
    domain = models.CharField(max_length=180, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    billing_email = models.EmailField(blank=True)
    account_owner = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.STANDARD)
    industry = models.CharField(max_length=120, blank=True)
    employee_count = models.PositiveIntegerField(null=True, blank=True)
    annual_revenue = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    address = models.TextField(blank=True)
    renewal_date = models.DateField(null=True, blank=True)
    health_score = models.PositiveSmallIntegerField(default=80)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["workspace", "name"]),
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "tier"]),
            models.Index(fields=["workspace", "created_at"]),
        ]

    def __str__(self):
        return self.name


class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="contacts")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=220)
    email = models.EmailField()
    phone = models.CharField(max_length=60, blank=True)
    title = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("workspace", "email")]
        indexes = [
            models.Index(fields=["workspace", "organization"]),
            models.Index(fields=["workspace", "email"]),
        ]

    def __str__(self):
        return self.name


class CRMImportJob(models.Model):
    class ImportType(models.TextChoices):
        ORGANIZATIONS = "organizations", "Organizations"
        CONTACTS = "contacts", "Contacts"

    class Status(models.TextChoices):
        PREVIEW = "preview", "Preview"
        IMPORTED = "imported", "Imported"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="crm_import_jobs")
    import_type = models.CharField(max_length=20, choices=ImportType.choices)
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREVIEW)
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "import_type"])]


class CRMImportRow(models.Model):
    class Resolution(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update existing"
        SKIP = "skip", "Skip"

    job = models.ForeignKey(CRMImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    data = models.JSONField(default=dict)
    errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    duplicate_object_id = models.UUIDField(null=True, blank=True)
    resolution = models.CharField(max_length=20, choices=Resolution.choices, default=Resolution.CREATE)
    created_object_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["row_number"]

# Create your models here.
