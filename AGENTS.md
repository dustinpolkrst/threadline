# Threadline Agent Notes

Threadline is a Django monolith for self-hosted support operations: CRM, tickets, customer portal, activity, and time tracking.

## Project Defaults

- Use `uv` for dependency management and command execution.
- Keep `pyproject.toml` and `uv.lock` as the dependency source of truth.
- Use Django templates plus HTMX. Do not introduce a separate SPA.
- Keep the architecture a modular monolith. Do not split into microservices.
- Optimize UI for dense desktop support workflows using Tailwind CSS.
- Prefer function-based views unless a local module establishes a different pattern.

## Security And Scoping Rules

- Scope every customer-data query by `workspace` first.
- Customer portal queries must also scope by the customer's `organization` and, where appropriate, `contact`.
- Customer users must never see internal comments, internal activity, private time entries, internal users, other customers, or workspace settings.
- Internal app access is based on `WorkspaceMembership`.
- Customer portal access is based on `CustomerProfile`.

## Local Commands

- Install dependencies: `uv sync`
- Run migrations: `uv run python manage.py migrate`
- Run dev server: `uv run python manage.py runserver`
- Run tests: `uv run pytest`
- Seed demo data: `uv run python manage.py seed_demo`

## Deployment Notes

- Local and single-VPS deployment use Docker Compose.
- Use environment variables for secrets, database, Redis, allowed hosts, CSRF, email, and debug mode.
- Production-style compose should run migrations and collectstatic before starting Gunicorn.
