import uuid

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
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


def first_workspace_for(user):
    if not user.is_authenticated:
        return None
    membership = user.workspace_memberships.select_related("workspace").first()
    return membership.workspace if membership else None

# Create your models here.
