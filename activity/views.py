from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from core.pagination import paginate
from core.permissions import require_internal_workspace
from .models import ActivityEvent


@login_required
def activity_log(request):
    workspace = require_internal_workspace(request.user)
    events = ActivityEvent.objects.filter(workspace=workspace).select_related("actor", "ticket", "organization", "contact")
    for key in ["event_type", "visibility"]:
        value = request.GET.get(key)
        if value:
            events = events.filter(**{key: value})
    if request.GET.get("actor"):
        events = events.filter(actor__username__icontains=request.GET["actor"])
    if request.GET.get("date_from"):
        events = events.filter(created_at__date__gte=request.GET["date_from"])
    if request.GET.get("date_to"):
        events = events.filter(created_at__date__lte=request.GET["date_to"])
    page_obj = paginate(request, events, per_page=50)
    return render(request, "activity/log.html", {"events": page_obj, "page_obj": page_obj, "filters": request.GET, "event_types": ActivityEvent.objects.filter(workspace=workspace).values_list("event_type", flat=True).distinct()})
