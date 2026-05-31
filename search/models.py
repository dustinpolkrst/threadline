import uuid

from django.contrib.postgres.search import SearchVectorField
from django.db import models
from workspaces.models import Workspace


class SearchDocument(models.Model):
    class EntityType(models.TextChoices):
        TICKET = "ticket", "Ticket"
        COMMENT = "comment", "Comment"
        ORGANIZATION = "organization", "Organization"
        CONTACT = "contact", "Contact"
        SOLUTION_SNIPPET = "solution_snippet", "Solution snippet"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="search_documents")
    entity_type = models.CharField(max_length=40, choices=EntityType.choices)
    object_id = models.UUIDField()
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    customer_visible = models.BooleanField(default=False)
    organization_id = models.UUIDField(null=True, blank=True)
    contact = models.ForeignKey("crm.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    search_vector = SearchVectorField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("workspace", "entity_type", "object_id")]
        indexes = [
            models.Index(fields=["workspace", "entity_type"]),
            models.Index(fields=["workspace", "organization_id", "customer_visible"]),
            models.Index(fields=["workspace", "organization_id", "contact", "customer_visible"]),
        ]

    def __str__(self):
        return f"{self.entity_type}: {self.title}"
