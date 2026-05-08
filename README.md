# Threadline

Threadline is an open-source CRM, ticketing, customer portal, and time tracking app for software support teams. It is a Django monolith using Django templates, HTMX, Tailwind CSS, PostgreSQL, Celery, Redis, and Docker Compose.

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

The app runs at `http://localhost:8000`.

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
- Email settings

Start services:

```bash
docker compose -f compose.yml -f compose.prod.yml up -d --build
```

The web container runs migrations and `collectstatic` before Gunicorn starts. In production, put Nginx, Caddy, or another reverse proxy in front of `127.0.0.1:8000` and terminate TLS there.

Persistent volumes are defined for PostgreSQL, Redis, uploaded media, and collected static files.

Health checks:

- PostgreSQL uses `pg_isready` in Compose.
- Django can be checked with `python manage.py check`.
- Celery can be checked with `celery -A config inspect ping`.

## Architecture Notes

- `workspaces`: tenant/workspace and internal membership.
- `crm`: organizations and contacts.
- `tickets`: tickets, public replies, internal notes, and attachment boundaries.
- `time_tracking`: manual time entries with billable and customer visibility flags.
- `activity`: internal and customer-visible activity events.
- `customer_portal`: restricted customer ticket flows.
- `search`: permission-scoped search, using PostgreSQL full-text search when running on PostgreSQL.

Customer portal access is represented by `CustomerProfile`. Internal access is represented by `WorkspaceMembership`. Customer-facing queries are scoped by workspace and organization, and sensitive internal comments, activity, and private time entries are filtered from portal views.
