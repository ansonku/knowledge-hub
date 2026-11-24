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
from .publication import article_card, category_index, path_of, presented, published_articles

WINDOW_DAYS = 30
OVERVIEW_DAYS = (7, 30)
SPARK_DAYS = 15
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


@never_cache
@api_view(["GET"])
@permission_classes([IsAdmin])
def public_overview(request):
    """P6a: Admin overview of the public site. Aggregates existing counts only; records nothing."""
    requested = request.query_params.get("days", "")
    days = int(requested) if requested in {str(option) for option in OVERVIEW_DAYS} else WINDOW_DAYS
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    first = min(start, today - timedelta(days=SPARK_DAYS - 1))
    publications = list(
        published_articles().values(
            "document_id", "title", "published_at", "version_id", "version__number",
            "document__current_version_id", "document__current_version__number", "document__category_id",
        )
    )
    ids = [row["document_id"] for row in publications]
    counts = {}
    for document_id, day, count in ArticleViewDaily.objects.filter(document_id__in=ids, day__gte=first).values_list(
            "document_id", "day", "count"):
        counts.setdefault(document_id, {})[day] = count
    window = [start + timedelta(days=offset) for offset in range(days)]
    spark_days = [today - timedelta(days=offset) for offset in range(SPARK_DAYS - 1, -1, -1)]
    index = category_index()
    articles = []
    for row in publications:
        daily = counts.get(row["document_id"], {})
        published, latest = row["version__number"], row["document__current_version__number"] or row["version__number"]
        articles.append({
            "document_id": row["document_id"], "title": row["title"], "published_at": row["published_at"],
            "path": path_of(row["document__category_id"], index),
            "published_version": published, "latest_version": latest, "behind": max(0, latest - published),
            "published_version_id": row["version_id"],
            "latest_version_id": row["document__current_version_id"] or row["version_id"],
            "total": sum(daily.get(day, 0) for day in window),
            "spark": [daily.get(day, 0) for day in spark_days],
        })
    articles.sort(key=lambda item: (-item["total"], item["title"]))
    totals = [{"day": day, "count": sum(counts.get(row["document_id"], {}).get(day, 0) for row in publications)} for day in window]
    return Response({
        "days": days,
        "total": sum(item["count"] for item in totals),
        "daily": totals,
        "articles": articles,
        "lagging": sum(1 for item in articles if item["behind"]),
        "idle": sum(1 for item in articles if not item["total"]),
    })
