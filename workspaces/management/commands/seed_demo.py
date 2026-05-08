from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from activity.services import record_event
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from workspaces.models import Workspace, WorkspaceMembership


class Command(BaseCommand):
    help = "Create demo workspace, internal user, customer user, CRM records, tickets, and time entries."

    def handle(self, *args, **options):
        User = get_user_model()
        workspace, _ = Workspace.objects.get_or_create(slug="demo", defaults={"name": "Demo Workspace"})
        agent, _ = User.objects.get_or_create(username="agent", defaults={"email": "agent@example.com"})
        agent.set_password("password")
        agent.save()
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=agent, defaults={"role": WorkspaceMembership.Role.OWNER})

        org, _ = Organization.objects.get_or_create(workspace=workspace, name="Acme Software", defaults={"domain": "acme.example"})
        contact, _ = Contact.objects.get_or_create(workspace=workspace, email="pat@acme.example", defaults={"organization": org, "name": "Pat Morgan"})
        customer, _ = User.objects.get_or_create(username="customer", defaults={"email": "pat@acme.example"})
        customer.set_password("password")
        customer.save()
        CustomerProfile.objects.get_or_create(user=customer, workspace=workspace, organization=org, contact=contact)

        samples = [
            {
                "title": "Cannot export weekly report",
                "description": "The CSV export fails after selecting last week.",
                "status": Ticket.Status.OPEN,
                "priority": Ticket.Priority.HIGH,
                "public": "This blocks our Monday reporting.",
                "internal": "Check export logs before replying.",
                "minutes": 35,
            },
            {
                "title": "SSO login loops after password reset",
                "description": "Users are redirected back to the identity provider after resetting passwords.",
                "status": Ticket.Status.PENDING,
                "priority": Ticket.Priority.URGENT,
                "public": "We can reproduce this with three affected users.",
                "internal": "Likely stale ACS URL in customer IdP configuration.",
                "minutes": 50,
            },
            {
                "title": "Invoice webhook retry question",
                "description": "The customer wants to know how long failed invoice webhooks are retried.",
                "status": Ticket.Status.NEW,
                "priority": Ticket.Priority.NORMAL,
                "public": "Can you confirm the retry schedule?",
                "internal": "Link to integration docs when replying.",
                "minutes": 15,
            },
            {
                "title": "Feature flag not visible in staging",
                "description": "A newly enabled feature flag is missing from the staging environment.",
                "status": Ticket.Status.RESOLVED,
                "priority": Ticket.Priority.NORMAL,
                "public": "The flag appeared after the cache was refreshed.",
                "internal": "Resolved by clearing the workspace flag cache.",
                "minutes": 25,
            },
        ]
        for sample in samples:
            ticket, _ = Ticket.objects.update_or_create(
                workspace=workspace,
                title=sample["title"],
                defaults={
                    "organization": org,
                    "contact": contact,
                    "requester": customer,
                    "description": sample["description"],
                    "status": sample["status"],
                    "priority": sample["priority"],
                    "source": Ticket.Source.PORTAL,
                },
            )
            TicketComment.objects.get_or_create(workspace=workspace, ticket=ticket, author=customer, body=sample["public"], visibility=TicketComment.Visibility.PUBLIC)
            TicketComment.objects.get_or_create(workspace=workspace, ticket=ticket, author=agent, body=sample["internal"], visibility=TicketComment.Visibility.INTERNAL)
            TimeEntry.objects.get_or_create(
                workspace=workspace,
                user=agent,
                ticket=ticket,
                organization=org,
                contact=contact,
                defaults={"started_at": timezone.now(), "duration_minutes": sample["minutes"], "billable": True, "customer_visible": True},
            )
            record_event(workspace=workspace, actor=agent, ticket=ticket, event_type="demo.seeded", summary=f"Seeded demo ticket: {ticket.title}", customer_visible=False)
        self.stdout.write(self.style.SUCCESS("Demo users: agent/password and customer/password"))
