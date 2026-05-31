from django.core.exceptions import ObjectDoesNotExist

from workspaces.theme import theme_context_for_workspace


def threadline_theme(request):
    workspace = _workspace_for_request(request)
    return {"threadline_theme": theme_context_for_workspace(workspace)}


def _workspace_for_request(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    membership = user.workspace_memberships.select_related("workspace").first()
    if membership is not None:
        return membership.workspace

    try:
        return user.customer_profile.workspace
    except ObjectDoesNotExist:
        return None
