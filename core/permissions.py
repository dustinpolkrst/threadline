from django.core.exceptions import PermissionDenied
from workspaces.models import first_workspace_for


def require_internal_workspace(user):
    workspace = first_workspace_for(user)
    if workspace is None:
        raise PermissionDenied("Internal workspace access required.")
    return workspace


def customer_profile_for(user):
    return getattr(user, "customer_profile", None)


def require_customer_profile(user):
    profile = customer_profile_for(user)
    if profile is None:
        raise PermissionDenied("Customer portal access required.")
    return profile
