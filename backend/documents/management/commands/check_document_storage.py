from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from documents.models import PendingDocumentDeletion, Version
from documents.services import STORAGE_LOCK_KEY
from documents.storage import root, sync_directory


class Command(BaseCommand):
    help = "Report missing and unreferenced version files, optionally moving unreferenced files to quarantine."

    def add_arguments(self, parser):
        parser.add_argument("--quarantine", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s), 0)", [STORAGE_LOCK_KEY])
        base = root()
        expected = set(Version.objects.values_list("path", flat=True))
        pending = {str(item) for item in PendingDocumentDeletion.objects.values_list("pk", flat=True)}
        present = {
            str(path.relative_to(base)) for path in (base / "versions").glob("*/*")
            if path.is_file() and path.parent.name not in pending
        }
        for path in sorted(present - expected):
            self.stdout.write(f"Unreferenced: {path}")
            if options["quarantine"]:
                source = base / path
                destination = base / "quarantine" / path
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if destination.exists():
                    raise CommandError(f"Quarantine destination already exists: {path}")
                source.rename(destination)
                sync_directory(source.parent)
                sync_directory(destination.parent)
        for path in sorted(expected - present):
            self.stderr.write(f"Missing: {path}")
        if expected - present:
            raise CommandError("Restore missing files from backup.")
        self.stdout.write(f"Checked {len(expected)} committed version files.")
