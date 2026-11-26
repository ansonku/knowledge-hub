"""P18: print the broken link report. Exits with status 1 when a link is broken (warnings alone pass)."""
import sys

from django.core.management.base import BaseCommand

from documents.linkcheck import scan


class Command(BaseCommand):
    help = "Report links to this site's documents, images and videos that no longer work, and media kept only by old versions."

    def handle(self, *args, **options):
        report = scan()
        summary = report["summary"]
        for document in report["documents"]:
            self.stdout.write(f"{document['title']} ({document['id']})")
            for item in document["issues"]:
                where = f"line {item['line']}" if item["line"] else f"published v{item.get('published_version')}"
                mark = "BROKEN " if item["severity"] == "broken" else "warning"
                self.stdout.write(f"  {mark} {where}: {item['reason']} — {item['text']}")
        storage = report["storage"]
        self.stdout.write(
            f"Checked {summary['checked']} documents: {summary['broken']} broken, {summary['warnings']} warnings "
            f"in {summary['documents']} documents. Media kept only by old versions: {len(storage['old_versions'])} "
            f"({storage['old_versions_bytes']} bytes); used by no version: {storage['unused']['images']} images, "
            f"{storage['unused']['videos']} videos.")
        if summary["broken"]:
            sys.exit(1)
