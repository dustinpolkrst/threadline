from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from activity.services import record_event
from crm.models import Contact, Organization
from customer_portal.models import CustomerProfile
from tickets.models import Ticket, TicketComment
from time_tracking.models import TimeEntry
from workspaces.models import Workspace, WorkspaceMembership
from communications.models import MailboxChannel


class Command(BaseCommand):
    help = "Create demo workspace, internal user, customer user, CRM records, tickets, and time entries."

    def handle(self, *args, **options):
        User = get_user_model()
        workspace, _ = Workspace.objects.get_or_create(slug="demo", defaults={"name": "Demo Workspace"})
        agent, _ = User.objects.get_or_create(username="agent", defaults={"email": "agent@example.com"})
        agent.set_password("password")
        agent.save()
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=agent, defaults={"role": WorkspaceMembership.Role.OWNER})
        MailboxChannel.objects.get_or_create(workspace=workspace, address="support@threadline.example", defaults={"name": "Support mailbox", "status": MailboxChannel.Status.STUBBED})

        org, _ = Organization.objects.update_or_create(
            workspace=workspace,
            name="Acme Software",
            defaults={
                "domain": "acme.example",
                "website": "https://acme.example",
                "phone": "+1 312 555 0184",
                "billing_email": "billing@acme.example",
                "account_owner": "Taylor Kim",
                "status": Organization.Status.ACTIVE,
                "tier": Organization.Tier.PRIORITY,
                "industry": "B2B SaaS",
                "employee_count": 180,
                "annual_revenue": "4200000.00",
                "address": "400 West Lake Street\nChicago, IL 60606",
                "health_score": 76,
                "notes": "Priority support customer. Engineering team relies on weekly exports and SSO access for operations reporting.",
            },
        )
        Organization.objects.update_or_create(
            workspace=workspace,
            name="Northstar Labs",
            defaults={
                "domain": "northstar.example",
                "website": "https://northstar.example",
                "phone": "+1 415 555 0142",
                "billing_email": "ap@northstar.example",
                "account_owner": "Morgan Lee",
                "status": Organization.Status.PROSPECT,
                "tier": Organization.Tier.STANDARD,
                "industry": "Developer tools",
                "employee_count": 42,
                "health_score": 88,
                "notes": "Evaluation account. Interested in customer portal and time reporting.",
            },
        )
        Organization.objects.update_or_create(
            workspace=workspace,
            name="Beacon Health Systems",
            defaults={
                "domain": "beacon.example",
                "phone": "+1 617 555 0198",
                "billing_email": "it-billing@beacon.example",
                "account_owner": "Riley Patel",
                "status": Organization.Status.AT_RISK,
                "tier": Organization.Tier.ENTERPRISE,
                "industry": "Healthcare software",
                "employee_count": 950,
                "health_score": 54,
                "notes": "Escalated account. Needs faster response on integration issues before renewal.",
            },
        )
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
            TimeEntry.objects.filter(workspace=workspace, user=agent, ticket=ticket).delete()
            TimeEntry.objects.create(
                workspace=workspace,
                user=agent,
                ticket=ticket,
                organization=org,
                contact=contact,
                started_at=timezone.now(),
                duration_minutes=sample["minutes"],
                billable=True,
                customer_visible=True,
            )
            record_event(workspace=workspace, actor=agent, ticket=ticket, event_type="demo.seeded", summary=f"Seeded demo ticket: {ticket.title}", customer_visible=False)
        self.stdout.write(self.style.SUCCESS("Demo users: agent/password and customer/password"))
