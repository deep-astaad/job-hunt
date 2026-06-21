"""New API views for the Next.js frontend."""
import json
import os
from datetime import date, timedelta

from django.db.models import Case, F, IntegerField, Subquery, OuterRef, Value, When
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Job, JobRanking
from .serializers import JobRankingBrowseSerializer


class BrowsePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


TIER_SORT = {t: i for i, t in enumerate(["S", "A", "B", "C", "F"])}


class BrowseView(APIView):
    permission_classes = [IsAuthenticated]

    """
    Paginated rankings + nested job for the Browse page.

    Query params:
      profile_id  (required)
      tiers       comma-separated, e.g. S,A,B  (default all)
      source      job source slug
      language    EN / JP / non-english
      location    free-text location filter (matches job.region or job.location)
      remote      true | false
      date        today | 3days | 7days | all  (default today)
      q           free-text search (title / company / description)
      page        page number
      page_size   rows per page (default 25, max 100)
    """

    def get(self, request):
        from django.db.models import Q

        profile_id = request.query_params.get("profile_id", "")
        tiers_param = request.query_params.get("tiers", "")
        source = request.query_params.get("source", "")
        language = request.query_params.get("language", "")
        location = request.query_params.get("location", "").strip()
        remote_param = request.query_params.get("remote", "")
        applied_param = request.query_params.get("applied", "")
        date_param = request.query_params.get("date", "today")
        q = request.query_params.get("q", "").strip()

        if profile_id == "all":
            # Deduplicate: one row per job, best tier across all profiles.
            # Correlated subquery returns the id of the best ranking for each job_id.
            best_id_sq = JobRanking.objects.filter(
                job_id=OuterRef("job_id")
            ).annotate(
                _tv=Case(
                    *[When(match_tier=t, then=Value(i)) for t, i in TIER_SORT.items()],
                    default=Value(99),
                    output_field=IntegerField(),
                )
            ).order_by("_tv", "rank").values("id")[:1]

            qs = JobRanking.objects.select_related("job").filter(
                job__is_active=True,
                id=Subquery(best_id_sq),
            )
        else:
            qs = JobRanking.objects.select_related("job").filter(job__is_active=True)
            if profile_id:
                qs = qs.filter(profile_id=profile_id)

        if tiers_param:
            tiers = [t.strip().upper() for t in tiers_param.split(",") if t.strip()]
            if tiers:
                qs = qs.filter(match_tier__in=tiers)

        if source:
            qs = qs.filter(job__source=source)

        if language:
            qs = qs.filter(job__language=language)

        if location:
            qs = qs.filter(
                Q(job__region__icontains=location)
                | Q(job__location__icontains=location)
                | Q(job__country__icontains=location)
            )

        if remote_param == "true":
            qs = qs.filter(job__is_remote=True)
        elif remote_param == "false":
            qs = qs.filter(job__is_remote=False)

        if applied_param == "true":
            qs = qs.filter(job__is_applied=True)
        elif applied_param == "false":
            qs = qs.filter(job__is_applied=False)

        if date_param == "today":
            qs = qs.filter(job__scraped_at__date=date.today())
        elif date_param == "3days":
            qs = qs.filter(job__scraped_at__date__gte=date.today() - timedelta(days=3))
        elif date_param == "7days":
            qs = qs.filter(job__scraped_at__date__gte=date.today() - timedelta(days=7))

        if q:
            qs = qs.filter(
                Q(job__title__icontains=q)
                | Q(job__company__icontains=q)
                | Q(job__description__icontains=q)
            )

        tier_order = Case(
            *[When(match_tier=t, then=Value(i)) for t, i in TIER_SORT.items()],
            default=Value(99),
            output_field=IntegerField(),
        )
        qs = qs.annotate(_tier_val=tier_order).order_by("_tier_val", "rank")

        paginator = BrowsePagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = JobRankingBrowseSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


def _load_profiles():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "user-profiles.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


class ProfilesView(APIView):
    permission_classes = [IsAuthenticated]

    """Return profiles list + available filter choices."""

    def get(self, request):
        profiles = _load_profiles()
        profiles = [{"id": "all", "title": "All Profiles (Combined)"}] + profiles
        # Distinct non-empty regions from DB for the location filter
        region_choices = (
            Job.objects.filter(region__gt="")
            .values_list("region", flat=True)
            .distinct()
            .order_by("region")[:30]
        )
        return Response({
            "profiles": profiles,
            "source_choices": [{"value": v, "label": l} for v, l in Job.SOURCE_CHOICES],
            "language_choices": [{"value": v, "label": l} for v, l in Job.LANGUAGE_CHOICES],
            "location_choices": [{"value": r, "label": r} for r in region_choices],
        })


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    """
    Cached analytics dashboard payload.
    GET /api/dashboard/?profile_id=<id>
    """

    def get(self, request):
        profile_id = request.query_params.get("profile_id", "")
        profiles = _load_profiles()

        if not profile_id and profiles:
            profile_id = profiles[0]["id"]

        from .insights import get_cached_dashboard
        payload = get_cached_dashboard(profile_id, profiles)
        return Response(payload)


class DashboardAlertView(APIView):
    permission_classes = [IsAuthenticated]

    """Return current Apify quota alert (if any)."""

    def get(self, request):
        try:
            import sys
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if root not in sys.path:
                sys.path.insert(0, root)
            from config import get_redis_client
            r = get_redis_client()
            if not r:
                return Response({"alert": None})
            raw = r.get("apify:quota_alert")
            import json as _json
            return Response({"alert": _json.loads(raw) if raw else None})
        except Exception:
            return Response({"alert": None})


class TriggerScrapeView(APIView):
    """Trigger the scraping pipeline (staff only)."""

    def post(self, request):
        if not request.user.is_staff:
            return Response({"error": "Forbidden"}, status=403)

        import sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)

        from tasks.pipeline import run_pipeline

        actor_configs_path = os.path.join(root, "actor-config.json")
        if not os.path.exists(actor_configs_path):
            return Response({"error": "actor-config.json not found"}, status=400)

        with open(actor_configs_path, "r") as f:
            actor_configs = json.load(f)

        profiles = _load_profiles()
        profile_ids = [p["id"] for p in profiles]

        source = request.data.get("source", "").strip()
        if source:
            actor_configs = [c for c in actor_configs if c.get("source") == source]
            if not actor_configs:
                return Response({"error": f"No actor config for source '{source}'"}, status=400)

        task = run_pipeline.delay(actor_configs, profile_ids)
        return Response({"status": "success", "task_id": task.id})


class TriggerProcessingView(APIView):
    """Trigger format+rank of unprocessed jobs (staff only)."""

    def post(self, request):
        if not request.user.is_staff:
            return Response({"error": "Forbidden"}, status=403)

        import sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)

        from tasks.pipeline import process_unprocessed_jobs_task

        profiles = _load_profiles()
        profile_ids = [p["id"] for p in profiles]
        task = process_unprocessed_jobs_task.delay(profile_ids)
        return Response({"status": "success", "task_id": task.id})
