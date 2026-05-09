from django.db.models import Q, Sum

from ai.views import ai_panel_context
from time_tracking.forms import TimeEntryForm, TimerStartForm, TimerStopForm
from time_tracking.models import ActiveTimer

from .forms import CommentForm, TicketAttachmentForm, TicketRelationForm
from .models import Ticket, TicketRelation
from .services import sla_state


def build_ticket_detail_context(request, workspace, ticket):
    time_entries = ticket.time_entries.filter(workspace=workspace).select_related("user")
    relations = TicketRelation.objects.filter(workspace=workspace).filter(Q(source=ticket) | Q(target=ticket))
    ticket.sla_state = sla_state(ticket)
    context = {
        "ticket": ticket,
        "comments": ticket.comments.filter(workspace=workspace).select_related("author"),
        "comment_form": CommentForm(),
        "time_form": TimeEntryForm(),
        "timer_start_form": TimerStartForm(),
        "timer_stop_form": TimerStopForm(),
        "active_timer": ActiveTimer.objects.filter(workspace=workspace, user=request.user).select_related("ticket").first(),
        "time_entries": time_entries,
        "time_total": time_entries.aggregate(total=Sum("duration_minutes"))["total"] or 0,
        "activity": ticket.activity_events.filter(workspace=workspace).select_related("actor"),
        "attachments": ticket.attachments.filter(workspace=workspace).select_related("uploaded_by"),
        "attachment_form": TicketAttachmentForm(),
        "relation_form": relation_form(workspace, ticket),
        "relations": relations.select_related("source", "target", "created_by"),
    }
    context.update(ai_panel_context(ticket, workspace))
    return context


def relation_form(workspace, ticket, data=None):
    form = TicketRelationForm(data)
    form.fields["target"].queryset = Ticket.objects.filter(workspace=workspace).exclude(pk=ticket.pk)
    return form
