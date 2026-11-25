from django.core.management.base import BaseCommand

from documents.images import GRACE, collect_unused_images
from documents.videos import collect_unused_videos


class Command(BaseCommand):
    help = "Remove pasted images and embedded videos that no version refers to, once their grace period has passed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be removed.")

    def handle(self, *args, **options):
        verb = "Would remove" if options["dry_run"] else "Removed"
        hours = int(GRACE.total_seconds() // 3600)
        for label, collect in (("images", collect_unused_images), ("videos", collect_unused_videos)):
            count, size = collect(dry_run=options["dry_run"])
            self.stdout.write(f"{verb} {count} unused {label} ({size} bytes) older than {hours} hours.")
