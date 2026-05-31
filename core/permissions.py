from django.core.exceptions import PermissionDenied
from workspaces.models import WorkspaceMembership


def require_internal_workspace(user):
    membership = _membership_for(user)
    if membership is None:
        raise PermissionDenied("Internal workspace access required.")
    return membership.workspace


def require_support_workspace(user):
    membership = _membership_for(user)
    if membership is None or membership.role not in [
        WorkspaceMembership.Role.OWNER,
        WorkspaceMembership.Role.ADMIN,
        WorkspaceMembership.Role.AGENT,
    ]:
        raise PermissionDenied("Workspace support access required.")
    return membership.workspace


def require_admin_workspace(user):
    membership = _membership_for(user)
    if membership is None or membership.role not in [
        WorkspaceMembership.Role.OWNER,
        WorkspaceMembership.Role.ADMIN,
    ]:
        raise PermissionDenied("Workspace admin access required.")
    return membership.workspace


def customer_profile_for(user):
    return getattr(user, "customer_profile", None)


def require_customer_profile(user):
    profile = customer_profile_for(user)
    if profile is None:
        raise PermissionDenied("Customer portal access required.")
    return profile


def _membership_for(user):
    if not user.is_authenticated:
        return None
    return user.workspace_memberships.select_related("workspace").first()
