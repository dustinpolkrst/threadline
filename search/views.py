from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from django.contrib.postgres.search import SearchQuery, SearchVector
from core.permissions import customer_profile_for, require_internal_workspace
from crm.models import Contact, Organization
from tickets.models import Ticket, TicketComment


@login_required
def search_page(request):
    q = request.GET.get("q", "").strip()
    profile = customer_profile_for(request.user)
    if profile:
        tickets = Ticket.objects.filter(workspace=profile.workspace, organization=profile.organization)
        comments = TicketComment.objects.filter(workspace=profile.workspace, ticket__organization=profile.organization, visibility=TicketComment.Visibility.PUBLIC)
        organizations = Organization.objects.none()
        contacts = Contact.objects.none()
    else:
        workspace = require_internal_workspace(request.user)
        tickets = Ticket.objects.filter(workspace=workspace)
        comments = TicketComment.objects.filter(workspace=workspace)
        organizations = Organization.objects.filter(workspace=workspace)
        contacts = Contact.objects.filter(workspace=workspace)
    if q:
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
            query = SearchQuery(q)
            tickets = tickets.annotate(search=SearchVector("title", "description", "tags")).filter(search=query)
            comments = comments.annotate(search=SearchVector("body")).filter(search=query)
        else:
            tickets = tickets.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q))
            comments = comments.filter(body__icontains=q)
        organizations = organizations.filter(Q(name__icontains=q) | Q(domain__icontains=q))
        contacts = contacts.filter(Q(name__icontains=q) | Q(email__icontains=q))
    return render(request, "search/search.html", {"q": q, "tickets": tickets[:20], "comments": comments[:20], "organizations": organizations[:20], "contacts": contacts[:20], "is_customer": bool(profile)})

# Create your views here.
