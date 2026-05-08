from .models import ActivityEvent


def record_event(*, workspace, event_type, summary, actor=None, ticket=None, organization=None, contact=None, customer_visible=False):
    return ActivityEvent.objects.create(
        workspace=workspace,
        actor=actor,
        ticket=ticket,
        organization=organization or (ticket.organization if ticket else None),
        contact=contact or (ticket.contact if ticket else None),
        event_type=event_type,
        summary=summary,
        visibility=ActivityEvent.Visibility.CUSTOMER if customer_visible else ActivityEvent.Visibility.INTERNAL,
    )
