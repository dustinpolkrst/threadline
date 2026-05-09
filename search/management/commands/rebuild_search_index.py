from django.core.management.base import BaseCommand, CommandError

from search.services import rebuild_workspace_index
from workspaces.models import Workspace


class Command(BaseCommand):
    help = "Rebuild Threadline search documents."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", help="Workspace slug or id to rebuild.")
        parser.add_argument("--clear", action="store_true", help="Delete matching search documents before rebuilding.")

    def handle(self, *args, **options):
        workspaces = Workspace.objects.all().order_by("slug")
        workspace_value = options.get("workspace")
        if workspace_value:
            workspaces = workspaces.filter(slug=workspace_value)
            if not workspaces.exists():
                workspaces = Workspace.objects.filter(pk=workspace_value)
            if not workspaces.exists():
                raise CommandError(f"Workspace not found: {workspace_value}")

        totals = {"ticket": 0, "comment": 0, "organization": 0, "contact": 0, "solution_snippet": 0}
        for workspace in workspaces:
            counts = rebuild_workspace_index(workspace, clear=options["clear"])
            for key, count in counts.items():
                totals[key] += count
            self.stdout.write(
                f"{workspace.slug}: "
                f"{counts['ticket']} tickets, {counts['comment']} comments, "
                f"{counts['organization']} organizations, {counts['contact']} contacts"
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Rebuilt search index: "
                f"{totals['ticket']} tickets, {totals['comment']} comments, "
                f"{totals['organization']} organizations, {totals['contact']} contacts"
            )
        )
