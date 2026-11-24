from django.core.management.base import BaseCommand, CommandError

from documents.consistency import QuarantineConflict, inspect_storage


class Command(BaseCommand):
    help = "Report missing and unreferenced version and image files, optionally moving unreferenced files to quarantine."

    def add_arguments(self, parser):
        parser.add_argument("--quarantine", action="store_true")

    def handle(self, *args, **options):
        try:
            checked, missing, unreferenced = inspect_storage(quarantine=options["quarantine"])
        except QuarantineConflict as conflict:
            raise CommandError(f"Quarantine destination already exists: {conflict}") from None
        for path in unreferenced:
            self.stdout.write(f"Unreferenced: {path}")
        for path in missing:
            self.stderr.write(f"Missing: {path}")
        if missing:
            raise CommandError("Restore missing files from backup.")
        self.stdout.write(f"Checked {checked} committed version and image files.")
