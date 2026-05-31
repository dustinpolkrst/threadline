from django.core.management.base import BaseCommand

from ai.services import prune_ai_generation_retention


class Command(BaseCommand):
    help = "Prune retained AI generated outputs while preserving audit metadata."

    def handle(self, *args, **options):
        pruned = prune_ai_generation_retention()
        self.stdout.write(self.style.SUCCESS(f"Pruned {pruned} AI run generation payload(s)."))
