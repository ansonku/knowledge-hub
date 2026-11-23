import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from django.http.request import split_domain_port
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from users.models import User
from users.permissions import CanReadLibrary, has_role

from . import storage
from .models import Document, PreviewTicket

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
TICKET_LIFETIME = timedelta(seconds=60)
PREVIEW_POLICY = "; ".join([
    "sandbox allow-scripts",
    "default-src 'none'",
    "script-src https: 'unsafe-inline'",
    "style-src https: 'unsafe-inline'",
    "img-src https: data: blob:",
    "font-src https: data:",
    "media-src https: data: blob:",
    "connect-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-src 'none'",
    "worker-src 'none'",
    "frame-ancestors 'self'",
])


def local_preview_enabled(request):
    configured_origin = urlsplit(settings.PUBLIC_ORIGIN)
    host, _ = split_domain_port(request.get_host())
    return (
        settings.LOCAL_HTML_PREVIEW
        and configured_origin.scheme == "http"
        and split_domain_port(configured_origin.netloc)[0] in LOCAL_HOSTS
        and host in LOCAL_HOSTS
        and not request.is_secure()
        and request.headers.get("X-Forwarded-Proto") != "https"
        and "CF-Connecting-IP" not in request.headers
    )


def ticket_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@never_cache
@api_view(["POST"])
@permission_classes([CanReadLibrary])
def issue_preview(request, document_id):
    if not local_preview_enabled(request):
        raise Http404
    document = get_object_or_404(Document, pk=document_id, format=Document.Format.HTML, is_trashed=False)
    if not document.current_version_id or str(document.current_version_id) != request.data.get("version"):
        return Response({"detail": "文件已有新版本，請重新載入。"}, status=409)

    now = timezone.now()
    PreviewTicket.objects.filter(expires_at__lte=now).delete()
    token = secrets.token_urlsafe(32)
    PreviewTicket.objects.create(
        digest=ticket_digest(token), version_id=document.current_version_id, user=request.user,
        session_version=request.user.session_version, expires_at=now + TICKET_LIFETIME,
    )
    return Response({"url": reverse("html-preview", kwargs={"token": token})}, status=201)


@never_cache
@require_GET
def html_preview(request, token):
    if not local_preview_enabled(request) or len(token) != 43 or not token.isascii():
        raise Http404

    with transaction.atomic():
        ticket = (
            PreviewTicket.objects.select_related("version__document", "user")
            .select_for_update(of=("self",))
            .filter(pk=ticket_digest(token), expires_at__gt=timezone.now())
            .first()
        )
        if ticket is None:
            raise Http404
        version = ticket.version
        document = version.document
        allowed = (
            has_role(ticket.user, *User.Role.values)
            and ticket.user.session_version == ticket.session_version
            and document.format == Document.Format.HTML
            and not document.is_trashed
            and document.current_version_id == version.pk
            and version.path == f"versions/{document.id}/{version.id}"
        )
        ticket.delete()
    if not allowed:
        raise Http404

    try:
        file = (storage.root() / version.path).open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(file, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = PREVIEW_POLICY
    response["Content-Disposition"] = "inline"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), fullscreen=()"
    return response
