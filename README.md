# Threadline

Threadline is an open-source, self-hostable support operations platform for small and mid-sized software teams. It combines CRM, ticketing, customer portal access, support activity, and time tracking in one Django monolith.

The goal is not to become a heavy enterprise suite. Threadline should be practical software that a support team can run on a single VPS with Docker Compose, understand, maintain, and adapt.

## Project Scope

Threadline is for software support teams that need:

- Customer and organization records.
- Ticket queues and ticket history.
- Internal support notes and activity.
- Customer portal ticket creation and replies.
- Customer portal account self-service and ticket filtering.
- Manual time tracking and billable time reporting.
- SLA tracking with priority policies and business-hours calendars.
- Saved queues, saved filters, and bulk ticket operations.
- Simple team and role management.
- Copyable invitation links for internal users and customer portal users.
- Ticket and email-message attachment records.
- Provider-neutral email plumbing that can later support real inbound and outbound email.
- AI-assisted ticket triage, reply drafting, CRM account intelligence, time cleanup, and queue recommendations with human approval before customer-visible output or record mutations.

Threadline is intentionally built as a modular monolith:

- Backend: Django
- Frontend: Django templates, HTMX, Tailwind CSS
- Database: PostgreSQL
- Background jobs: Celery and Redis
- Packaging and commands: `uv`
- Deployment: Docker Compose

We are intentionally avoiding Kubernetes, microservices, a separate SPA, GraphQL, event sourcing, and managed-platform assumptions.

## Current MVP Features

- Workspace tenancy and internal workspace membership.
- Internal roles: owner, admin, agent, viewer.
- Organizations and contacts.
- Ticket CRUD with statuses, priority, assignee, requester, source, and due date.
- Customer portal ticket list/detail/create/reply.
- Customer portal dashboard filtering and basic account management.
- Internal ticket comments.
- Markdown rendering for ticket descriptions and comments with HTML sanitization.
- Ticket activity timeline.
- Filterable workspace audit/activity log.
- Manual time entries, billable flags, timer start/stop, and editable time entries.
- Ticket-level time ledger.
- Monthly time reports with CSV export.
- Saved queues: my open, unassigned, SLA at risk, recently updated, waiting on customer.
- Saved ticket filters and bulk queue actions.
- SLA target settings, priority SLA policies, business-hours calendars, and SLA state badges.
- Ticket link, duplicate, and merge records.
- Ticket attachment upload/download/delete with permission checks.
- Email message attachment metadata for future provider integration.
- Team settings for role changes, customer portal user review, and copyable invite links.
- CSV import preview/confirm flow for organizations and contacts.
- CSV import templates and duplicate-resolution controls.
- PostgreSQL full-text search ranking, highlighting, and rebuildable search documents.
- Optional local or S3-compatible private attachment storage.
- OpenRouter AI settings with encrypted provider keys, ZDR routing, per-feature controls, and Celery-backed generation jobs.
- AI ticket workbench with agent briefs, customer sentiment, urgency reasoning, next-best-action guidance, similar tickets, reply drafts, internal notes, triage suggestions, and selected human-approved application.
- AI reply composer for internal agents, including generate, shorten, expand with steps, and customer-safe rewrite flows. Customer replies remain drafts until approved by an internal user.
- AI solution memory records with approve/reject controls and approved snippet indexing in permission-scoped search.
- AI CRM account briefings with recurring issues, support tone, product areas, risks, recommended next touch, and hygiene suggestions.
- AI time-entry suggestions and a time cleanup page for likely unlogged work.
- AI queue intelligence dashboard for likely urgent tickets, stale pending work, missing customer info, probable duplicates, SLA risks, and high-effort accounts.
- AI audit console with auditable runs, suggested action outcomes, reply/snippet artifacts, token usage, latency, provider generation IDs, and privacy mode.
- Email plumbing models and stub services, without real provider integration.
- Docker Compose development and production-style deployment.
- Demo seed data and permission tests.

## Email Scope

Threadline currently includes email-ready plumbing only:

- Mailbox placeholders.
- Normalized email message records.
- Ingest logs.
- Delivery attempt records.
- Email attachment metadata.
- Stub service functions.
- Stub Celery tasks.

Threadline does **not** currently connect to IMAP, SMTP, Gmail, Microsoft Graph, Postmark, SES, SendGrid, Mailgun, or webhook providers. It also does not send invitation emails yet. Invitation links are generated in-app and copied manually. The current goal is to make future email integration straightforward without prematurely committing to a provider.

## Roadmap And TODOs

Recently completed:

- [x] Provider-neutral email plumbing.
- [x] Saved support queues.
- [x] Basic SLA target settings.
- [x] SLA state badges.
- [x] Team role management.
- [x] Customer portal user review.
- [x] Monthly time reports.
- [x] CSV export for time reports.
- [x] Editable time entries.
- [x] Attachments for tickets and email message records.
- [x] Better customer portal dashboard and ticket filtering.
- [x] Customer portal account management.
- [x] Copyable invitation links for internal users and customer users.
- [x] Priority SLA policies and business-hours calendars.
- [x] Ticket merge/link/duplicate workflows.
- [x] Saved filters with user preferences.
- [x] Bulk ticket actions.
- [x] PostgreSQL full-text ranking polish.
- [x] CSV import for organizations and contacts.
- [x] Better audit log filtering.
- [x] Markdown support for comments.
- [x] S3-compatible attachment storage option.
- [x] Search index rebuild command and richer highlighting.
- [x] Import templates and duplicate-resolution UI.
- [x] OpenRouter AI foundation with encrypted keys, structured outputs, Celery jobs, and ticket analysis polling.
- [x] AI agent-assist workbench, reply composer, solution memory, CRM intelligence, time cleanup, queue intelligence, and expanded AI audit.

High-priority next steps:

- [ ] Real inbound email-to-ticket integration.
- [ ] Outbound ticket replies by email.
- [ ] AI cost controls, generation retention settings, and admin-visible usage charts.
- [ ] Optional vector/embedding retrieval for approved solution memory and historical support context.
- [ ] SLA escalation notifications after email is configured.
- [ ] Public API endpoints for integrations where needed.

Longer-term possibilities:

- [ ] Customer-facing AI self-service after email and approval workflows are mature.
- [ ] Webhook integrations.
- [ ] Custom fields for tickets, contacts, and organizations.
- [ ] Per-organization support plans.
- [ ] More advanced reporting.
- [ ] Meilisearch or another dedicated search backend.
- [ ] Optional OAuth/SAML/SSO for self-hosters.

## Open Source Maintenance Goals

Threadline should be a community-friendly project. That means:

- Keep setup simple and documented.
- Prefer boring, durable architecture over cleverness.
- Keep dependencies understandable and justified.
- Maintain `pyproject.toml` and `uv.lock`.
- Keep Docker Compose as the primary deployment path.
- Write tests for permission boundaries and tenant scoping.
- Treat workspace and customer-data isolation as non-negotiable.
- Avoid introducing paid or platform-specific services as requirements.
- Make features useful for real support teams, not just impressive in demos.

Contribution priorities:

- Fix bugs before adding large features.
- Improve documentation when behavior changes.
- Add focused tests with new behavior.
- Keep UI dense, readable, and practical for daily support work.
- Preserve the modular monolith structure.

## Local Development

Prerequisites:

- Python 3.13
- `uv`
- Docker and Docker Compose if using PostgreSQL/Redis locally

Install dependencies:

```bash
uv sync
```

Run with SQLite for quick app work:

```bash
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```

Demo users after seeding:

- Internal agent: `agent` / `password`
- Customer portal user: `customer` / `password`

Run tests:

```bash
uv run pytest
```

## Docker Compose Development

Create an environment file:

```bash
cp .env.example .env
```

Start PostgreSQL, Redis, Django, and Celery:

```bash
docker compose up --build
```

Seed demo data inside the web container:

```bash
docker compose exec web python manage.py seed_demo
```

The app runs at `http://localhost:8000` unless `WEB_PORT` is set in `.env`.

After changing dependencies or application code, rebuild and recreate the running app services so Docker uses the new image:

```bash
docker compose build
docker compose up -d --force-recreate web celery
```

The web container runs migrations and `collectstatic` during startup.

## Production-Style Single VPS Deployment

Use the base compose file plus the production override:

```bash
cp .env.example .env
```

Edit `.env` and set:

- `SECRET_KEY`
- `DEBUG=false`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- PostgreSQL credentials
- `REDIS_URL`
- Email placeholders
- Media storage settings, if using S3-compatible attachment storage

Start services:

```bash
docker compose -f compose.yml -f compose.prod.yml up -d --build
```

The web container runs migrations and `collectstatic` before Gunicorn starts. In production, put Nginx, Caddy, or another reverse proxy in front of `127.0.0.1:8000` and terminate TLS there.

Persistent volumes are defined for PostgreSQL, Redis, uploaded media, and collected static files.

Attachment storage defaults to local private media. For S3-compatible storage, either set `MEDIA_STORAGE_BACKEND=s3` with the `AWS_*` values in `.env`, or configure a provider from Settings -> Application storage as an owner/admin. Objects remain private and Threadline still streams downloads through Django permission checks. Existing local media is not migrated automatically when switching storage backends.

AI is configured from Settings -> AI by an owner/admin. The first provider is OpenRouter, with draft-only agent-assist workflows by default, ZDR routing required for client ticket history, and opt-in manual application of AI triage suggestions. Provider keys are encrypted with `THREADLINE_FIELD_ENCRYPTION_KEY` in production.

Current AI workflows include ticket analysis, agent reply drafts, selected suggestion approval, solution memory generation, CRM account briefings, time-entry suggestions, workspace digests, queue intelligence, and audit history. Customer-visible messages and record mutations still require an internal user to approve the draft or selected suggestion.

AI jobs require a running Celery worker; Threadline does not fall back to running model calls in the web request. Provider connectivity can be checked with:

```bash
uv run python manage.py test_ai_provider --workspace demo
```

Rebuild search documents after large data imports or maintenance:

```bash
uv run python manage.py rebuild_search_index --clear
```

Health checks:

- PostgreSQL uses `pg_isready` in Compose.
- Django can be checked with `python manage.py check`.
- Celery can be checked with `celery -A config inspect ping`.

## Architecture Notes

- `workspaces`: tenants, internal membership, roles, invitations, SLA defaults, SLA policies, and business-hours calendars.
- `crm`: organizations, contacts, account details, CSV imports, and team settings views.
- `tickets`: tickets, comments, workflow fields, SLA state, queues, saved filters, bulk actions, relations, merges, and attachments.
- `time_tracking`: manual time, timers, editable entries, reports.
- `activity`: internal and customer-visible activity events with filtering.
- `customer_portal`: restricted customer ticket flows, dashboard filters, attachments, and account management.
- `communications`: provider-neutral email plumbing, email attachment metadata, and stub tasks.
- `search`: permission-scoped search, PostgreSQL full-text ranking, and a replaceable search document model.
- `ai`: OpenRouter provider settings, structured AI workflows, ticket analyses, reply drafts, suggested actions, CRM insights, time suggestions, digests, queue intelligence snapshots, solution memory, and audit records.

Customer portal access is represented by `CustomerProfile`. Internal access is represented by `WorkspaceMembership`. Customer-facing queries are scoped by workspace and organization, and sensitive internal comments, internal activity, private time entries, internal users, and workspace settings must not leak into the customer portal.

## Security And Data Isolation

Every feature must preserve these rules:

- Scope customer data by workspace first.
- Scope customer portal data by workspace and the customer user's organization/contact.
- Customer users cannot access internal comments, internal activity, private time entries, internal users, email logs, reports, or workspace settings.
- Internal users only see data for workspaces where they have membership.
- Admin/settings views require owner or admin roles.

These rules should be covered by tests whenever related behavior changes.
