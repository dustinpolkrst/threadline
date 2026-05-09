from django.conf import settings
from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank, SearchVector
from django.db.models import Q, Value
from django.urls import reverse
from django.utils.html import conditional_escape, escape
from django.utils.safestring import mark_safe

from crm.models import Contact, Organization
from tickets.models import Ticket, TicketComment

from .models import SearchDocument


POSTGRES_ENGINE = "django.db.backends.postgresql"


def uses_postgres():
    return settings.DATABASES["default"]["ENGINE"] == POSTGRES_ENGINE


def rebuild_workspace_index(workspace, clear=False):
    if clear:
        SearchDocument.objects.filter(workspace=workspace).delete()
    counts = {
        "ticket": 0,
        "comment": 0,
        "organization": 0,
        "contact": 0,
    }
    for ticket in Ticket.objects.filter(workspace=workspace).select_related("organization", "contact"):
        index_ticket(ticket, refresh_vector=False)
        counts["ticket"] += 1
    for comment in TicketComment.objects.filter(workspace=workspace).select_related("ticket", "ticket__organization"):
        index_comment(comment, refresh_vector=False)
        counts["comment"] += 1
    for organization in Organization.objects.filter(workspace=workspace):
        index_organization(organization, refresh_vector=False)
        counts["organization"] += 1
    for contact in Contact.objects.filter(workspace=workspace).select_related("organization"):
        index_contact(contact, refresh_vector=False)
        counts["contact"] += 1
    if uses_postgres():
        refresh_search_vectors(workspace)
    return counts


def index_ticket(ticket, refresh_vector=True):
    organization = ticket.organization
    contact = ticket.contact
    title = ticket.title
    body_parts = [ticket.description, ticket.tags]
    if organization:
        body_parts.extend([organization.name, organization.domain])
    if contact:
        body_parts.extend([contact.name, contact.email])
    doc = _upsert_document(
        workspace=ticket.workspace,
        entity_type=SearchDocument.EntityType.TICKET,
        object_id=ticket.pk,
        title=title,
        body="\n".join(part for part in body_parts if part),
        customer_visible=organization is not None,
        organization_id=organization.pk if organization else None,
    )
    if refresh_vector:
        _refresh_document_vector(doc)
    return doc


def index_comment(comment, refresh_vector=True):
    ticket = comment.ticket
    organization = ticket.organization
    doc = _upsert_document(
        workspace=comment.workspace,
        entity_type=SearchDocument.EntityType.COMMENT,
        object_id=comment.pk,
        title=f"Comment on {ticket.title}",
        body=comment.body,
        customer_visible=comment.visibility == TicketComment.Visibility.PUBLIC and organization is not None,
        organization_id=organization.pk if organization else None,
    )
    if refresh_vector:
        _refresh_document_vector(doc)
    return doc


def index_organization(organization, refresh_vector=True):
    body = "\n".join(
        part
        for part in [
            organization.domain,
            organization.website,
            organization.phone,
            organization.billing_email,
            organization.account_owner,
            organization.industry,
            organization.address,
            organization.notes,
        ]
        if part
    )
    doc = _upsert_document(
        workspace=organization.workspace,
        entity_type=SearchDocument.EntityType.ORGANIZATION,
        object_id=organization.pk,
        title=organization.name,
        body=body,
        customer_visible=False,
        organization_id=organization.pk,
    )
    if refresh_vector:
        _refresh_document_vector(doc)
    return doc


def index_contact(contact, refresh_vector=True):
    body = "\n".join(part for part in [contact.email, contact.phone, contact.title, contact.notes, contact.organization.name] if part)
    doc = _upsert_document(
        workspace=contact.workspace,
        entity_type=SearchDocument.EntityType.CONTACT,
        object_id=contact.pk,
        title=contact.name,
        body=body,
        customer_visible=False,
        organization_id=contact.organization_id,
    )
    if refresh_vector:
        _refresh_document_vector(doc)
    return doc


def search_documents_for_user(user, query_text, entity="all"):
    from core.permissions import customer_profile_for, require_internal_workspace

    profile = customer_profile_for(user)
    if profile:
        documents = SearchDocument.objects.filter(
            workspace=profile.workspace,
            organization_id=profile.organization_id,
            customer_visible=True,
        )
    else:
        workspace = require_internal_workspace(user)
        documents = SearchDocument.objects.filter(workspace=workspace)

    type_map = {
        "tickets": SearchDocument.EntityType.TICKET,
        "comments": SearchDocument.EntityType.COMMENT,
        "organizations": SearchDocument.EntityType.ORGANIZATION,
        "contacts": SearchDocument.EntityType.CONTACT,
    }
    if entity in type_map:
        documents = documents.filter(entity_type=type_map[entity])

    query_text = query_text.strip()
    if not query_text:
        return [], bool(profile)

    if uses_postgres():
        query = SearchQuery(query_text)
        documents = (
            documents.annotate(
                rank=SearchRank("search_vector", query),
                headline=SearchHeadline("body", query, start_sel="<mark>", stop_sel="</mark>", max_words=24, min_words=8),
            )
            .filter(search_vector=query)
            .order_by("-rank", "-updated_at")[:50]
        )
        docs = list(documents)
        comment_ticket_map = _comment_ticket_map(docs)
        results = [_document_result(doc, doc.headline or doc.body, profile, comment_ticket_map) for doc in docs]
    else:
        docs = list(documents.filter(Q(title__icontains=query_text) | Q(body__icontains=query_text)).order_by("-updated_at")[:50])
        comment_ticket_map = _comment_ticket_map(docs)
        results = [_document_result(doc, _plain_snippet(doc, query_text), profile, comment_ticket_map) for doc in docs]
    return results, bool(profile)


def refresh_search_vectors(workspace=None):
    if not uses_postgres():
        return 0
    documents = SearchDocument.objects.all()
    if workspace:
        documents = documents.filter(workspace=workspace)
    return documents.update(search_vector=SearchVector("title", weight="A") + SearchVector("body", weight="B"))


def _upsert_document(**values):
    doc, _ = SearchDocument.objects.update_or_create(
        workspace=values["workspace"],
        entity_type=values["entity_type"],
        object_id=values["object_id"],
        defaults={
            "title": values["title"],
            "body": values["body"],
            "customer_visible": values["customer_visible"],
            "organization_id": values["organization_id"],
        },
    )
    return doc


def _refresh_document_vector(doc):
    if uses_postgres():
        SearchDocument.objects.filter(pk=doc.pk).update(search_vector=SearchVector("title", weight="A") + SearchVector("body", weight="B"))


def _plain_snippet(doc, query_text):
    haystack = doc.body or doc.title
    lower = haystack.lower()
    needle = query_text.lower()
    position = lower.find(needle)
    if position < 0:
        return escape(haystack[:180])
    start = max(position - 70, 0)
    end = min(position + len(query_text) + 110, len(haystack))
    prefix = "..." if start else ""
    suffix = "..." if end < len(haystack) else ""
    before = escape(haystack[start:position])
    match = escape(haystack[position : position + len(query_text)])
    after = escape(haystack[position + len(query_text) : end])
    return mark_safe(f"{prefix}{before}<mark>{match}</mark>{after}{suffix}")


def _document_result(doc, snippet, profile, comment_ticket_map=None):
    return {
        "document": doc,
        "badge": doc.get_entity_type_display(),
        "title": doc.title,
        "snippet": mark_safe(snippet) if "<mark>" in str(snippet) else conditional_escape(snippet),
        "url": _document_url(doc, bool(profile), comment_ticket_map or {}),
    }


def _document_url(doc, is_customer, comment_ticket_map=None):
    if doc.entity_type == SearchDocument.EntityType.TICKET:
        return reverse("portal_ticket_detail" if is_customer else "ticket_detail", args=[doc.object_id])
    if doc.entity_type == SearchDocument.EntityType.COMMENT:
        ticket_id = (comment_ticket_map or {}).get(doc.object_id)
        if ticket_id:
            return reverse("portal_ticket_detail" if is_customer else "ticket_detail", args=[ticket_id])
    if not is_customer and doc.entity_type == SearchDocument.EntityType.ORGANIZATION:
        return reverse("organization_detail", args=[doc.object_id])
    if not is_customer and doc.entity_type == SearchDocument.EntityType.CONTACT:
        return reverse("contact_detail", args=[doc.object_id])
    return "#"


def _comment_ticket_map(docs):
    comment_ids = [doc.object_id for doc in docs if doc.entity_type == SearchDocument.EntityType.COMMENT]
    if not comment_ids:
        return {}
    return dict(TicketComment.objects.filter(pk__in=comment_ids).values_list("pk", "ticket_id"))
