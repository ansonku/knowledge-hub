import codecs
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError


def root():
    return Path(settings.DOCUMENT_STORAGE)


@contextmanager
def stage(upload):
    directory = root() / "staging"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    sha = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")()
    size = 0
    with tempfile.NamedTemporaryFile(dir=directory) as temporary:
        try:
            for chunk in upload.chunks():
                size += len(chunk)
                if size > settings.DOCUMENT_MAX_BYTES:
                    raise ValidationError({"file": "檔案超過大小上限。"})
                decoder.decode(chunk)
                sha.update(chunk)
                temporary.write(chunk)
            decoder.decode(b"", final=True)
        except UnicodeError:
            raise ValidationError({"file": "檔案必須使用 UTF-8 編碼。"}) from None
        if not size:
            raise ValidationError({"file": "檔案不得為空。"})
        temporary.flush()
        os.fsync(temporary.fileno())
        yield Path(temporary.name), sha.hexdigest(), size


def sync_directory(path):
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(temporary, document_id, version_id):
    directory = root() / "versions"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = directory / str(document_id)
    folder.mkdir(mode=0o700, exist_ok=True)
    destination = folder / str(version_id)
    os.link(temporary, destination)
    sync_directory(folder)
    sync_directory(directory)
    sync_directory(root())
    return str(destination.relative_to(root()))
