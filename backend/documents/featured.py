"""P6b: featured articles on the public home (decision 17).

Admins pick up to four published articles and their order. The public home lists them after
"popular", and the popular ranking skips them (decision 18). Withdrawing or trashing an article
removes it (publication.withdraw_publication); republishing does not bring it back.
"""
from django.db import transaction
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from users.permissions import IsAdmin

from . import activity
from .models import FeaturedArticle, SiteSettings
from .covers import add_covers
from .publication import article_card, category_index, path_of, presented, published_articles

MAX_FEATURED = 4


def featured_ids():
    """Featured documents that are still published, in order."""
    published = set(published_articles().values_list("document_id", flat=True))
    return [pk for pk in FeaturedArticle.objects.values_list("document_id", flat=True) if pk in published]


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_featured(request):
    ids = featured_ids()
    rows = {row["document_id"]: row for row in presented(published_articles().filter(pk__in=ids))}
    index = category_index()
    return Response({"results": add_covers([article_card(rows[pk], index) for pk in ids if pk in rows], public=True)})


class FeaturedInput(serializers.Serializer):
    documents = serializers.ListField(child=serializers.UUIDField(), max_length=MAX_FEATURED, allow_empty=True)


def admin_payload():
    ids = featured_ids()
    rows = {row["document_id"]: row for row in published_articles().filter(pk__in=ids).values("document_id", "title", "document__category_id")}
    index = category_index()
    return {"max": MAX_FEATURED, "results": [
        {"document_id": pk, "title": rows[pk]["title"], "path": path_of(rows[pk]["document__category_id"], index)} for pk in ids
    ]}


@never_cache
@api_view(["GET", "PUT"])
@permission_classes([IsAdmin])
def manage_featured(request):
    """GET the list; PUT {documents: [ids]} replaces it (adding, removing and reordering in one call)."""
    if request.method == "GET":
        return Response(admin_payload())
    payload = FeaturedInput(data=request.data)
    payload.is_valid(raise_exception=True)
    wanted = payload.validated_data["documents"]
    if len(set(wanted)) != len(wanted):
        raise ValidationError({"documents": "同一篇文章只能精選一次。"})
    with transaction.atomic():
        # The site settings row serialises concurrent edits of the list.
        SiteSettings.objects.select_for_update().get_or_create(pk=1)
        published = set(published_articles().filter(pk__in=wanted).values_list("document_id", flat=True))
        if missing := [pk for pk in wanted if pk not in published]:
            raise ValidationError({"documents": f"只能精選公開中的文章（{len(missing)} 篇不符合）。"})
        before = set(FeaturedArticle.objects.values_list("document_id", flat=True))
        FeaturedArticle.objects.all().delete()
        FeaturedArticle.objects.bulk_create([FeaturedArticle(document_id=pk, position=i) for i, pk in enumerate(wanted)])
        for pk in wanted:
            if pk not in before:
                activity.record(pk, request.user, activity.Action.FEATURED)
        for pk in before - set(wanted):
            activity.record(pk, request.user, activity.Action.UNFEATURED)
    return Response(admin_payload())
