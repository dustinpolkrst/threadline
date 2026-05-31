# Production Readiness

Threadline is designed for a single VPS deployment with Docker Compose, PostgreSQL, Redis, Celery, and a TLS-terminating reverse proxy.

## Required Configuration

- Set `SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`.
- Set TLS/proxy flags for production: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`, and `USE_X_FORWARDED_PROTO`.
- Set `THREADLINE_FIELD_ENCRYPTION_KEY` before configuring AI provider keys or mailbox passwords.
- Run PostgreSQL and Redis with persistent volumes.
- Run a Celery worker for AI generation, email polling, outbound email delivery, and pruning jobs.

## Private Media

- Local media is private and streamed through Django permission checks.
- For S3-compatible storage, set `MEDIA_STORAGE_BACKEND=s3` with the `AWS_*` values before starting the app.
- Storage credentials are deployment-scoped environment variables, not workspace database settings.

## Email

- Global Django SMTP settings (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`) provide the default outbound backend.
- Workspace mailbox channels can override outbound SMTP and enable inbound IMAP polling.
- Mailbox IMAP/SMTP passwords are encrypted with `THREADLINE_FIELD_ENCRYPTION_KEY`.
- Inbound email is idempotent by `(workspace, message_id)`.
- Outbound email records delivery attempts and failures for audit.

## AI Operations

- Configure OpenRouter in workspace settings.
- Use monthly token and run caps to bound spend.
- Use generation retention days to prune generated payloads and context while preserving audit metadata.
- Run `uv run python manage.py prune_ai_generations` on a schedule, or call the Celery task from your scheduler.

## Verification

Run these checks before deployment:

```bash
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
uv run python manage.py check --deploy
```
