from django.core.management.base import BaseCommand
from django.db.models import F
from django.http import Http404

from documents import search, storage
from documents.models import Version


class Command(BaseCommand):
    help = "Index the current versions of documents created before full-text search was enabled."

    def handle(self, *args, **options):
        pending = Version.objects.filter(
            search_text__isnull=True, pk=F("document__current_version_id"),
        ).select_related("document")
        for version in pending.iterator(chunk_size=25):
            try:
                with storage.open_version(version, version.document_id) as stream:
                    text = search.extract(stream, version.document.format)
            except (Http404, OSError, UnicodeError):
                self.stderr.write(f"Could not index version {version.pk}.")
            else:
                Version.objects.filter(pk=version.pk, search_text__isnull=True).update(search_text=text)
