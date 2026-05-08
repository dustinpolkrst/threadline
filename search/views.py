from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
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
            ticket_vector = SearchVector("title", weight="A") + SearchVector("description", weight="B") + SearchVector("tags", weight="C")
            tickets = tickets.annotate(search=ticket_vector, rank=SearchRank(ticket_vector, query)).filter(search=query).order_by("-rank", "-updated_at")
            comment_vector = SearchVector("body", weight="B")
            comments = comments.annotate(search=comment_vector, rank=SearchRank(comment_vector, query)).filter(search=query).order_by("-rank", "-created_at")
        else:
            tickets = tickets.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q))
            comments = comments.filter(body__icontains=q)
        organizations = organizations.filter(Q(name__icontains=q) | Q(domain__icontains=q))
        contacts = contacts.filter(Q(name__icontains=q) | Q(email__icontains=q))
    entity = request.GET.get("type", "all")
    return render(request, "search/search.html", {"q": q, "entity": entity, "tickets": tickets[:50] if entity in ["all", "tickets"] else [], "comments": comments[:50] if entity in ["all", "comments"] else [], "organizations": organizations[:50] if entity in ["all", "organizations"] else [], "contacts": contacts[:50] if entity in ["all", "contacts"] else [], "is_customer": bool(profile)})

# Create your views here.
