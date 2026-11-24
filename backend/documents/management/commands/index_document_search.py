from django.core.management.base import BaseCommand

from documents.maintenance import index_missing


class Command(BaseCommand):
    help = "Index the current versions of documents created before full-text search was enabled."

    def handle(self, *args, **options):
        result = index_missing()
        if result["failed"]:
            self.stderr.write(f"Could not index {result['failed']} versions.")
