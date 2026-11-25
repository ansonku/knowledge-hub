"""P13: links between documents.

A link is an ordinary Markdown link whose address names a document by id: /app/docs/<id>/, /read/<id>/ or
/articles/<id>/, optionally with this site's origin in front and ?…/#… after. Every new version records the
documents it links to; backlinks count current versions only. Readers only ever learn about documents they
can read.
"""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from users.models import User
from users.permissions import CanReadLibrary, has_role

from . import services
from .models import Document, VersionLink

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
PATH = re.compile(rf"(?<![\w/])((?:https?://[^\s/)<>\"']+)?)/(?:app/docs|read|articles)/({UUID})(?=[/?#)\s>\"']|$)", re.I)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[`~]*[ \t]*$|\Z)", re.M | re.S)
INLINE_CODE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.S)


def site_hosts():
    """Host names this site answers to: PUBLIC_ORIGIN's, plus ALLOWED_HOSTS (people copy addresses from either)."""
    hosts = {urlsplit(settings.PUBLIC_ORIGIN).hostname or ""}
    hosts |= {host.lstrip(".") for host in settings.ALLOWED_HOSTS if host and host != "*"}
    return {host.lower() for host in hosts if host}


def linked_ids(text):
    """Ids of the documents a Markdown text links to, in order of first appearance. Code is not links."""
    text = INLINE_CODE.sub(" ", FENCE.sub("\n", text))
    hosts, seen = site_hosts(), []
    for origin, pk in PATH.findall(text):
        if origin and (urlsplit(origin).hostname or "").lower() not in hosts:
            continue
        pk = pk.lower()
        if pk not in seen:
            seen.append(pk)
    return seen


def record_links(version, text):
    ids = [pk for pk in linked_ids(text) if pk != str(version.document_id)]
    VersionLink.objects.bulk_create([VersionLink(version=version, target_id=pk) for pk in ids], ignore_conflicts=True)


def summary(document):
    return {
        "id": str(document.pk), "title": document.title, "format": document.format,
        "category": document.category_id, "category_name": document.category.name if document.category_id else None,
        "updated_at": document.updated_at,
    }


def resolve(ids, user):
    """{id: {status, …}} for documents a member asks about: ok (with title), trashed or missing.
    Titles of trashed documents are for Editors and Admins, who can open the trash."""
    found = {str(document.pk): document for document in Document.objects.select_related("category").filter(pk__in=ids)}
    sees_trash = has_role(user, User.Role.ADMIN, User.Role.EDITOR)
    result = {}
    for pk in ids:
        document = found.get(pk)
        if document is None:
            result[pk] = {"status": "missing"}
        elif document.is_trashed:
            result[pk] = {"status": "trashed", **({"title": document.title} if sees_trash else {})}
        else:
            result[pk] = {"status": "ok", **summary(document)}
    return result


def incoming(document_ids, exclude=()):
    """Documents (not in the trash) whose current version links to any of `document_ids`."""
    links = VersionLink.objects.filter(version=OuterRef("current_version"), target_id__in=document_ids)
    return services.active_documents().filter(Exists(links)).exclude(pk__in=[*document_ids, *exclude])


class IdList(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=200)


def ids_from(request):
    raw = [value for value in request.query_params.get("ids", "").split(",") if value]
    form = IdList(data={"ids": raw})
    if not form.is_valid():
        raise ValidationError({"ids": "請提供 1 至 200 個文件 id。"})
    return [str(pk) for pk in dict.fromkeys(form.validated_data["ids"])]


@api_view(["GET"])
@permission_classes([CanReadLibrary])
def document_links(request, document_id):
    """The documents linking here, and where this document links to (with each target's state)."""
    document = get_object_or_404(services.active_documents().select_related("current_version"), pk=document_id)
    sources = incoming([str(document.pk)]).select_related("category").order_by("-updated_at")
    targets = list(VersionLink.objects.filter(version=document.current_version).order_by("pk").values_list("target_id", flat=True))
    resolved = resolve([str(pk) for pk in targets], request.user)
    return Response({
        "incoming": [summary(source) for source in sources],
        "outgoing": [{"id": pk, **state} for pk, state in resolved.items()],
    })


@api_view(["GET"])
@permission_classes([CanReadLibrary])
def resolve_links(request):
    """What the reading page needs to mark links: GET /api/documents/resolve/?ids=a,b."""
    return Response(resolve(ids_from(request), request.user))


@api_view(["GET"])
@permission_classes([CanReadLibrary])
def incoming_counts(request):
    """Before moving documents to the trash: how many other documents link to each. ?ids=a,b"""
    ids = ids_from(request)
    counts = {}
    for pk in ids:
        counts[pk] = incoming([pk], exclude=ids).count()
    return Response(counts)
