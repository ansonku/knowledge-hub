"""P24c: the About page and the getting-started card in the management centre (Admins)."""
from allauth.mfa.models import Authenticator
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from documents.models import Category, Document
from users.models import AuditLog, User
from users.permissions import IsAdmin

from . import about


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def about_page(request):
    """The software, its developer and terms, and who accepted which terms version when (from the audit log)."""
    def name(row):
        # create_hub_admin records the new admin as the target only (and rows before P24 have no actor).
        person = row.actor or row.target
        return (person.display_name or person.username) if person else None
    accepted = [{
        "by": name(row), "at": row.created_at, "via": row.metadata.get("via", "command"),
        "terms_version": row.metadata.get("terms_version"),
    } for row in AuditLog.objects.filter(action="admin_bootstrapped").select_related("actor", "target").order_by("created_at")]
    return Response({**about.public(), "accepted": accepted})


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def getting_started(request):
    """What a new site still needs, worked out from its data (nothing is stored)."""
    tasks = {
        "admin": True,
        "members": User.objects.exclude(pk=request.user.pk).exists(),
        "collections": Category.objects.exists(),
        "documents": Document.objects.filter(is_trashed=False).exists(),
        "mfa": Authenticator.objects.filter(user=request.user).exists(),
    }
    return Response({"tasks": tasks, "done": sum(tasks.values()), "total": len(tasks)})
