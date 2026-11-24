from django.core.management.base import BaseCommand

from documents.maintenance import retry_deletions


class Command(BaseCommand):
    help = "Retry file cleanup for confirmed permanent deletions."

    def handle(self, *args, **options):
        result = retry_deletions()
        if result["failed"]:
            self.stderr.write(f"Cleanup pending for {result['failed']} documents.")
