from django.conf import settings
from django.db import models
from crm.models import Contact, Organization
from workspaces.models import Workspace


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="customer_profiles")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="customer_profiles")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="customer_profiles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["workspace", "organization", "contact"])]

    def __str__(self):
        return f"{self.user} portal profile"

# Create your models here.
