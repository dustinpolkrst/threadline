from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.utils import timezone

from ai.client import OpenRouterError, send_chat_completion
from ai.services import get_ai_settings
from workspaces.models import Workspace


class Command(BaseCommand):
    help = "Test the configured AI provider for a workspace."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True, help="Workspace slug or id")

    def handle(self, *args, **options):
        value = options["workspace"]
        workspace = Workspace.objects.filter(slug=value).first()
        if not workspace:
            try:
                workspace = Workspace.objects.filter(pk=value).first()
            except ValidationError:
                workspace = None
        if not workspace:
            raise CommandError(f"Workspace not found: {value}")
        ai_settings = get_ai_settings(workspace)
        messages = [
            {"role": "system", "content": "Return a small JSON health response."},
            {"role": "user", "content": "Threadline AI provider health check."},
        ]
        try:
            response = send_chat_completion(ai_settings, messages, max_tokens=200, structured=False)
        except OpenRouterError as exc:
            ai_settings.last_test_status = "failed"
            ai_settings.last_test_message = str(exc)[:500]
            ai_settings.last_tested_at = timezone.now()
            ai_settings.save(update_fields=["last_test_status", "last_test_message", "last_tested_at", "updated_at"])
            raise CommandError(str(exc))
        ai_settings.last_test_status = "ok"
        ai_settings.last_test_message = f"Provider returned {response.get('model', 'unknown model')}"
        ai_settings.last_tested_at = timezone.now()
        ai_settings.save(update_fields=["last_test_status", "last_test_message", "last_tested_at", "updated_at"])
        self.stdout.write(self.style.SUCCESS(ai_settings.last_test_message))
