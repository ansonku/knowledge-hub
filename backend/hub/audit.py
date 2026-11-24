"""Admin audit trail: account events, document activity and permanent deletions in one feed.

Read-only. Rows come from three tables merged with a SQL UNION and ordered by time:
  * users.AuditLog            → "account" (admin actions, profile changes) and "signin"
  * documents.DocumentActivity → "document", "publish" and "trash"
  * documents.DocumentTrashAudit (action "permanent") → "deletion"; the activity rows of a
    permanently deleted document go away with it, so this keeps its title and version count.
Account metadata is filtered to a whitelist so nothing secret can reach the response.
"""
from django.db.models import CharField, F, IntegerField, UUIDField, Value
from django.db.models.functions import Cast, JSONObject
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from documents.models import DocumentActivity, DocumentTrashAudit
from users.models import AuditLog, User
from users.permissions import IsAdmin

PAGE_SIZE = 50
MAX_PAGE = 200
SIGNIN_ACTIONS = ("login", "logout")
PUBLISH_ACTIONS = (
    DocumentActivity.Action.PUBLISHED, DocumentActivity.Action.WITHDRAWN,
    DocumentActivity.Action.FEATURED, DocumentActivity.Action.UNFEATURED,
)
TRASH_ACTIONS = (DocumentActivity.Action.TRASHED, DocumentActivity.Action.RESTORED)
CATEGORIES = ("account", "signin", "document", "publish", "trash", "deletion")
# "maintenance" holds counts only (see hub.maintenance), never paths.
ACCOUNT_DETAIL_KEYS = ("reason", "role", "old_role", "identity_verified", "maintenance")


class AuditQuery(serializers.Serializer):
    category = serializers.ChoiceField(CATEGORIES, required=False)
    actor = serializers.UUIDField(required=False)
    member = serializers.UUIDField(required=False)
    since = serializers.DateTimeField(required=False)
    until = serializers.DateTimeField(required=False)
    page = serializers.IntegerField(min_value=1, max_value=MAX_PAGE, required=False, default=1)
    # Sign-ins are frequent; the unfiltered view hides them unless asked.
    signins = serializers.BooleanField(required=False, default=True)


def columns(query, *, source, key, target_user, document, title, detail, version):
    """Project each source onto the same column list so the querysets can be UNIONed."""
    return query.annotate(
        row_source=Value(source, output_field=CharField()), row_key=key, row_target_user=target_user,
        row_document=document, row_title=title, row_detail=detail, row_version=version,
    ).values_list(
        "row_source", "row_key", "action", "created_at", "actor_id",
        "row_target_user", "row_document", "row_title", "row_detail", "row_version",
    ).order_by()


def bounded(query, data):
    if "actor" in data:
        query = query.filter(actor_id=data["actor"])
    if "since" in data:
        query = query.filter(created_at__gte=data["since"])
    if "until" in data:
        query = query.filter(created_at__lt=data["until"])
    return query


def sources(data):
    category = data.get("category")
    no_uuid, no_text = Value(None, output_field=UUIDField()), Value(None, output_field=CharField())
    no_number = Value(None, output_field=IntegerField())
    parts = []
    if category in (None, "account", "signin"):
        accounts = bounded(AuditLog.objects.all(), data)
        if category == "account":
            accounts = accounts.exclude(action__in=SIGNIN_ACTIONS)
        elif category == "signin":
            accounts = accounts.filter(action__in=SIGNIN_ACTIONS)
        elif not data["signins"]:
            accounts = accounts.exclude(action__in=SIGNIN_ACTIONS)
        if "member" in data:
            accounts = accounts.filter(target_id=data["member"])
        parts.append(columns(
            accounts, source="account", key=Cast("pk", CharField()), target_user=F("target_id"),
            document=no_uuid, title=no_text, detail=F("metadata"), version=no_number,
        ))
    if "member" in data:
        return parts  # member filter: account events about that person only
    if category in (None, "document", "publish", "trash"):
        activity = bounded(DocumentActivity.objects.all(), data)
        if category == "document":
            activity = activity.exclude(action__in=(*PUBLISH_ACTIONS, *TRASH_ACTIONS))
        elif category == "publish":
            activity = activity.filter(action__in=PUBLISH_ACTIONS)
        elif category == "trash":
            activity = activity.filter(action__in=TRASH_ACTIONS)
        parts.append(columns(
            activity, source="activity", key=Cast("pk", CharField()), target_user=no_uuid,
            document=F("document_id"), title=F("document__title"), detail=F("detail"), version=F("version_number"),
        ))
    if category in (None, "deletion"):
        deletions = bounded(DocumentTrashAudit.objects.filter(action="permanent"), data)
        parts.append(columns(
            deletions, source="deletion", key=Cast("pk", CharField()), target_user=no_uuid,
            document=F("document_id"), title=F("title"),
            detail=JSONObject(version_count=F("version_count")), version=no_number,
        ))
    return parts


def category_of(source, action):
    if source == "deletion":
        return "deletion"
    if source == "account":
        return "signin" if action in SIGNIN_ACTIONS else "account"
    if action in PUBLISH_ACTIONS:
        return "publish"
    return "trash" if action in TRASH_ACTIONS else "document"


def person(user):
    return {"id": str(user.pk), "name": user.display_name or user.username} if user else None


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_feed(request):
    query = AuditQuery(data=request.query_params)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    parts = sources(data)
    page = data["page"]
    start = (page - 1) * PAGE_SIZE
    union = parts[0].union(*parts[1:], all=True) if len(parts) > 1 else parts[0]
    rows = list(union.order_by("-created_at", "-row_key")[start:start + PAGE_SIZE + 1])
    people = {user.pk: user for user in User.objects.filter(
        pk__in={value for row in rows for value in (row[4], row[5]) if value})}
    results = []
    for source, key, action, created_at, actor_id, target_user, document, title, detail, version in rows[:PAGE_SIZE]:
        detail = detail or {}
        if source == "account":
            detail = {name: detail[name] for name in ACCOUNT_DETAIL_KEYS if name in detail}
        results.append({
            "id": f"{source}:{key}", "category": category_of(source, action), "action": action,
            "created_at": created_at, "actor": person(people.get(actor_id)),
            "member": person(people.get(target_user)) if source == "account" else None,
            "document": {"id": str(document), "title": title, "deleted": source == "deletion"} if document else None,
            "version_number": version, "detail": detail,
        })
    return Response({"page": page, "has_more": len(rows) > PAGE_SIZE, "results": results})
