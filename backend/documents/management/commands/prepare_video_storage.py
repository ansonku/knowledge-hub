import os

from django.core.management.base import BaseCommand

from documents import storage
from documents.videos import FOLDER_MODE


class Command(BaseCommand):
    help = "Create DOCUMENT_STORAGE/videos/ before nginx starts: nginx mounts that folder, read-only, to serve videos."

    def handle(self, *args, **options):
        folder = storage.root() / "videos"
        folder.mkdir(exist_ok=True)
        os.chmod(folder, FOLDER_MODE)
