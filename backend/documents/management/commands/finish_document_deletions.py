from django.core.management.base import BaseCommand

from documents.models import PendingDocumentDeletion
from documents.trash import finish_permanent_deletion


class Command(BaseCommand):
    help = "Retry file cleanup for confirmed permanent deletions."

    def handle(self, *args, **options):
        for document_id in PendingDocumentDeletion.objects.values_list("pk", flat=True).iterator():
            if not finish_permanent_deletion(document_id):
                self.stderr.write(f"Cleanup pending for document {document_id}.")
