import uuid

from django.db import models
from workspaces.models import Workspace


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="organizations")
    name = models.CharField(max_length=220)
    domain = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["workspace", "name"]),
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

# Create your models here.
