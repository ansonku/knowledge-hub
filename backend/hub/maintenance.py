"""Run the maintenance steps on demand (Admin only), one run at a time, recorded in the audit log."""
import logging

from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from documents.maintenance import STEPS
from users.lifecycle import audit
from users.models import AuditLog
from users.permissions import IsAdmin

logger = logging.getLogger(__name__)

ACTION = "maintenance_run"
LOCK = "hub:maintenance-running"
# Long enough for any run; a crashed run frees the lock after this.
LOCK_SECONDS = 600


class MaintenanceRunning(APIException):
    status_code = 409
    default_detail = "維護作業正在執行中，請稍後再試。"
    default_code = "maintenance_running"


def run(actor):
    if not cache.add(LOCK, actor.pk, LOCK_SECONDS):
        raise MaintenanceRunning()
    started = timezone.now()
    results = {}
    try:
        for name, step in STEPS:
            # One failing step never stops the others.
            try:
                results[name] = step()
            except Exception:
                logger.exception("Maintenance step %s failed.", name)
                results[name] = {"error": True}
    finally:
        cache.delete(LOCK)
    audit(ACTION, actor, actor=actor, maintenance=results)
    return {"started_at": started, "finished_at": timezone.now(), "results": results}


def last_run():
    entry = AuditLog.objects.filter(action=ACTION).select_related("actor").order_by("-created_at").first()
    if entry is None:
        return None
    actor = entry.actor
    return {
        "at": entry.created_at,
        "actor": (actor.display_name or actor.username) if actor else None,
        "results": entry.metadata.get("maintenance", {}),
    }


@never_cache
@api_view(["POST"])
@permission_classes([IsAdmin])
def run_maintenance(request):
    return Response(run(request.user))
