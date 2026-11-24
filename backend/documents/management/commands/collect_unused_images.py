from django.core.management.base import BaseCommand

from documents.images import GRACE, collect_unused_images


class Command(BaseCommand):
    help = "Remove pasted images that no version refers to, once their grace period has passed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be removed.")

    def handle(self, *args, **options):
        count, size = collect_unused_images(dry_run=options["dry_run"])
        verb = "Would remove" if options["dry_run"] else "Removed"
        hours = int(GRACE.total_seconds() // 3600)
        self.stdout.write(f"{verb} {count} unused images ({size} bytes) older than {hours} hours.")
