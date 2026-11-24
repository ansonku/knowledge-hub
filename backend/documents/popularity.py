"""Popular public articles (P5e, decision 15).

Visitors' browsers report one view per article per day (deduplicated client side); the server only
keeps a per-article daily count. Requests are rate limited per client address; the throttle's cache
keys are SHA-256 hashed (users.security.cache_key) and expire, so no address is stored.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from users.permissions import IsAdmin

from .models import ArticleViewDaily, Document
from .publication import article_card, category_index, presented, published_articles

WINDOW_DAYS = 30
POPULAR_LIMIT = 5
POPULAR_MINIMUM = 3  # show the section only once this many articles have views


class ViewThrottle(SimpleRateThrottle):
    scope = "article_view"
    rate = "120/hour"

    def get_cache_key(self, request, view):
        # Nginx overwrites X-Hub-Client-IP with the real peer address; REMOTE_ADDR is the proxy.
        address = request.META.get("HTTP_X_HUB_CLIENT_IP") or request.META.get("REMOTE_ADDR", "")
        return self.cache_format % {"scope": self.scope, "ident": address}


def count_view(document_id, day):
    for _ in range(2):
        if ArticleViewDaily.objects.filter(document_id=document_id, day=day).update(count=F("count") + 1):
            return
        try:
            with transaction.atomic():
                ArticleViewDaily.objects.create(document_id=document_id, day=day, count=1)
            return
        except IntegrityError:
            continue  # created concurrently: the next loop updates it


@never_cache
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ViewThrottle])
def record_public_view(request, document_id):
    get_object_or_404(published_articles(), pk=document_id)
    count_view(document_id, timezone.localdate())
    return Response(status=204)


def window_start():
    return timezone.localdate() - timedelta(days=WINDOW_DAYS - 1)


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def popular_articles(request):
    totals = dict(
        ArticleViewDaily.objects.filter(day__gte=window_start(), document__articlepublication__isnull=False,
                                        document__is_trashed=False)
        .values_list("document_id").annotate(total=Sum("count"))
    )
    if len(totals) < POPULAR_MINIMUM:
        return Response({"results": []})
    ranked = sorted(totals, key=lambda pk: (-totals[pk], str(pk)))[:POPULAR_LIMIT]
    rows = {row["document_id"]: row for row in presented(published_articles().filter(pk__in=ranked))}
    index = category_index()
    # Counts stay private: the ranking is the only thing visitors see.
    return Response({"results": [article_card(rows[pk], index) for pk in ranked if pk in rows]})


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def document_public_views(request, document_id):
    get_object_or_404(Document.objects.filter(is_trashed=False), pk=document_id)
    start = window_start()
    counts = dict(ArticleViewDaily.objects.filter(document_id=document_id, day__gte=start).values_list("day", "count"))
    daily = [{"day": start + timedelta(days=offset), "count": counts.get(start + timedelta(days=offset), 0)}
             for offset in range(WINDOW_DAYS)]
    return Response({"days": WINDOW_DAYS, "total": sum(counts.values()), "daily": daily})
