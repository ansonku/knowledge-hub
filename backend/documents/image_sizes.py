"""Picture sizes for gallery layouts (P11b), which need each picture's shape before it loads.

Kept apart from documents.images so the publication views can use it without importing services.
"""
from .models import DocumentImage


def sizes(images):
    """{image id: [width, height]}."""
    return {str(pk): [width, height] for pk, width, height in images.values_list("pk", "width", "height")}


def version_image_sizes(version):
    """Sizes of the document's own images this version refers to (what its readers can load)."""
    if version is None:
        return {}
    return sizes(DocumentImage.objects.filter(document_id=version.document_id, references__version=version))
