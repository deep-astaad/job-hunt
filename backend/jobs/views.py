import hashlib
from datetime import date

import django_filters
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Min, Case, When, Value, IntegerField
from .models import Job, JobRanking
from .serializers import (
    JobSerializer,
    JobListSerializer,
    JobRankingSerializer,
    TodayRankedJobSerializer,
)
from .parsers import normalize_url


class TodayRankedJobFilter(django_filters.FilterSet):
    profile_id = django_filters.CharFilter(field_name="rankings__profile_id")
    tiers = django_filters.CharFilter(method="filter_tiers")

    class Meta:
        model = Job
        fields = ["profile_id", "tiers", "alert_sent"]

    def filter_tiers(self, queryset, name, value):
        tiers = [t.strip().upper() for t in value.split(",") if t.strip()]
        if tiers:
            return queryset.filter(rankings__match_tier__in=tiers)
        return queryset


class JobFilter(django_filters.FilterSet):
    updated_at = django_filters.DateFilter(field_name="updated_at", lookup_expr="date")

    class Meta:
        model = Job
        fields = ["source", "is_active", "language", "company", "is_formatted", "url",
                  "alert_sent", "region", "country", "is_remote"]

    def __init__(self, data=None, *args, **kwargs):
        # Alias ?from=... and ?to=... to updated_at date lookups
        if data:
            data = data.dict()
            if "from" in data:
                data["from_date"] = data.pop("from")
            if "to" in data:
                data["to_date"] = data.pop("to")
        super().__init__(data=data, *args, **kwargs)

    from_date = django_filters.DateFilter(field_name="updated_at", lookup_expr="date__gte")
    to_date = django_filters.DateFilter(field_name="updated_at", lookup_expr="date__lte")


TIER_SORT_MAP = {t: i for i, t in enumerate(["S", "A", "B", "C", "F"])}


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    filterset_class = JobFilter
    search_fields = ["title", "company", "description", "url"]
    ordering_fields = ["scraped_at", "company", "title", "best_tier"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            tier_case = Case(
                *[When(rankings__match_tier=t, then=Value(i)) for t, i in TIER_SORT_MAP.items()],
                default=Value(99),
                output_field=IntegerField(),
            )
            qs = qs.annotate(_best_tier_int=Min(tier_case)).distinct()
            ordering = self.request.query_params.get("ordering", "")
            if "best_tier" in ordering:
                desc = ordering.startswith("-")
                qs = qs.order_by(("-" if desc else "") + "_best_tier_int")
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return JobListSerializer
        return JobSerializer

    @action(detail=False, methods=["post"])
    def bulk_create(self, request):
        jobs_data = request.data if isinstance(request.data, list) else request.data.get("jobs", [])
        created, updated = 0, 0
        errors = []
        # Keyed by normalized URL; lets callers avoid a follow-up GET per job.
        job_map = {}

        for job_data in jobs_data:
            url = job_data.get("url")
            if not url:
                errors.append({"error": "url is required", "data": job_data})
                continue

            normalized_url = normalize_url(url)
            url_hash = hashlib.sha256(normalized_url.encode()).hexdigest()

            # Full record used only when creating a brand-new row.
            create_defaults = {
                "url": normalized_url,
                "title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
                "source": job_data.get("source", "custom"),
                "salary": job_data.get("salary", ""),
                "description": job_data.get("description", ""),
                "full_description": job_data.get("full_description", ""),
                "tech_stack": job_data.get("tech_stack"),
                "language": job_data.get("language"),
                "experience_required": job_data.get("experience_required", ""),
                "location": job_data.get("location", ""),
                "is_formatted": job_data.get("is_formatted", False),
                "raw_data": job_data.get("raw_data"),
            }

            # Non-destructive update set for re-seen rows: only refresh a field
            # when the incoming payload actually carries a meaningful value, so a
            # blank re-scrape stub can't wipe previously formatted data (which
            # would also reset is_ranked via Job.save and force a costly
            # re-format + re-rank). The formatter's bulk_create fallback still
            # updates real content because its values are non-empty.
            update_defaults = {"url": normalized_url}
            for key in (
                "title", "company", "source", "salary", "description",
                "full_description", "tech_stack", "language",
                "experience_required", "location",
            ):
                val = job_data.get(key)
                if val in (None, "", []):
                    continue
                # Don't let a missing-title sentinel clobber a real one.
                if key in ("title", "company") and val == "Unknown":
                    continue
                update_defaults[key] = val
            if job_data.get("raw_data") is not None:
                update_defaults["raw_data"] = job_data["raw_data"]
            # Only ever promote is_formatted to True; never downgrade it here.
            if job_data.get("is_formatted"):
                update_defaults["is_formatted"] = True

            try:
                obj, was_created = Job.objects.update_or_create(
                    url_hash=url_hash,
                    defaults=update_defaults,
                    create_defaults=create_defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                job_map[normalized_url] = {"id": obj.id, "is_formatted": obj.is_formatted}
            except Exception as e:
                errors.append({"error": str(e), "url": url})

        return Response(
            {"created": created, "updated": updated, "errors": errors, "jobs": job_map},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def rankings(self, request, pk=None):
        job = self.get_object()
        rankings = job.rankings.all()
        serializer = JobRankingSerializer(rankings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        total = Job.objects.count()
        active = Job.objects.filter(is_active=True).count()
        formatted = Job.objects.filter(is_formatted=True).count()
        ranked = Job.objects.filter(is_ranked=True).count()
        by_source = list(
            Job.objects.values("source")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        by_tier = list(
            JobRanking.objects.values("match_tier")
            .annotate(count=Count("id"))
            .order_by("match_tier")
        )
        return Response({
            "total_jobs": total,
            "active_jobs": active,
            "formatted_jobs": formatted,
            "ranked_jobs": ranked,
            "by_source": by_source,
            "by_tier": by_tier,
        })

    @action(detail=False, methods=["post"], url_path="mark_alerts_sent")
    def mark_alerts_sent(self, request):
        job_ids = request.data.get("job_ids", [])
        if not job_ids:
            return Response({"error": "job_ids required"}, status=status.HTTP_400_BAD_REQUEST)
        updated = Job.objects.filter(id__in=job_ids).update(alert_sent=True)
        return Response({"updated": updated}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="today-ranked")
    def today_ranked(self, request):
        today = date.today()

        tiers_param = request.query_params.get("tiers", "S,A")
        tiers = [t.strip().upper() for t in tiers_param.split(",") if t.strip()] or ["S", "A"]

        # Apply FilterSet for profile_id and tiers filtering
        base_qs = Job.objects.filter(is_active=True, scraped_at__date=today).distinct()
        filterset = TodayRankedJobFilter(request.query_params, queryset=base_qs)
        jobs = filterset.qs.distinct().prefetch_related("rankings")

        # Sort: requested tiers in order (S first, A second, etc.), then by rank
        tier_sort_map = {t: i for i, t in enumerate(["S", "A", "B", "C", "F"])}
        tier_order = Case(
            *[When(rankings__match_tier=t, then=Value(tier_sort_map.get(t, 99))) for t in tiers],
            default=Value(99),
            output_field=IntegerField(),
        )
        jobs = jobs.annotate(_tier_order=tier_order).order_by("_tier_order", "rankings__rank")

        # Attach ranking metadata for serializer
        rankings_filter = Q(match_tier__in=tiers)
        profile_id = request.query_params.get("profile_id")
        if profile_id:
            rankings_filter &= Q(profile_id=profile_id)

        results = []
        for job in jobs:
            matching_rankings = job.rankings.filter(rankings_filter)
            primary = matching_rankings.order_by(
                Case(
                    *[When(match_tier=t, then=Value(tier_sort_map.get(t, 99))) for t in tiers],
                    default=Value(99),
                    output_field=IntegerField(),
                ),
                "rank"
            ).first()
            if not primary:
                continue
            job._primary_ranking = primary
            job._matched_rankings = list(matching_rankings)
            results.append(job)

        serializer = TodayRankedJobSerializer(results, many=True)
        return Response({
            "count": len(results),
            "date": today.isoformat(),
            "results": serializer.data,
        })

    @action(detail=False, methods=["get"], url_path="today-all-rankings")
    def today_all_rankings(self, request):
        """Return today's jobs with ALL per-profile rankings (not just primary)."""
        today = date.today()
        jobs = Job.objects.filter(
            is_active=True, scraped_at__date=today
        ).prefetch_related("rankings").distinct()

        results = []
        for job in jobs:
            all_rankings = [
                {
                    "profile_id": r.profile_id,
                    "match_tier": r.match_tier,
                    "rank": r.rank,
                    "jd_summary": r.jd_summary,
                }
                for r in job.rankings.all()
            ]
            if not all_rankings:
                continue
            results.append({
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "rankings": all_rankings,
            })

        return Response({
            "count": len(results),
            "date": today.isoformat(),
            "results": results,
        })


class JobRankingFilter(django_filters.FilterSet):
    class Meta:
        model = JobRanking
        fields = ["profile_id", "match_tier"]


class JobRankingViewSet(viewsets.ModelViewSet):
    queryset = JobRanking.objects.select_related("job").all()
    serializer_class = JobRankingSerializer
    filterset_class = JobRankingFilter
    ordering_fields = ["rank", "created_at"]

    @action(detail=False, methods=["post"])
    def bulk_create(self, request):
        rankings_data = request.data if isinstance(request.data, list) else request.data.get("rankings", [])
        created, updated = 0, 0
        errors = []

        for rank_data in rankings_data:
            job_id = rank_data.get("job_id")
            profile_id = rank_data.get("profile_id")
            if not job_id or not profile_id:
                errors.append({"error": "job_id and profile_id are required", "data": rank_data})
                continue

            try:
                job = Job.objects.get(id=job_id)
            except Job.DoesNotExist:
                errors.append({"error": f"Job {job_id} not found"})
                continue

            try:
                defaults = {
                    "profile_title": rank_data.get("profile_title", ""),
                    "match_tier": rank_data.get("match_tier", "C"),
                    "rank": rank_data.get("rank", 0),
                    "jd_summary": rank_data.get("jd_summary", ""),
                }
                if rank_data.get("llm_tier"):
                    defaults["llm_tier"] = rank_data["llm_tier"]
                if rank_data.get("deterministic_tier"):
                    defaults["deterministic_tier"] = rank_data["deterministic_tier"]
                if rank_data.get("match_score") is not None:
                    defaults["match_score"] = rank_data["match_score"]
                if rank_data.get("signals") is not None:
                    defaults["signals"] = rank_data["signals"]
                obj, was_created = JobRanking.objects.update_or_create(
                    job=job,
                    profile_id=profile_id,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append({"error": str(e)})

        return Response(
            {"created": created, "updated": updated, "errors": errors},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="update_ranks")
    def update_ranks(self, request):
        """Bulk-update the rank field on existing JobRanking rows."""
        updates = request.data if isinstance(request.data, list) else request.data.get("updates", [])
        updated = 0
        errors = []

        for item in updates:
            job_id = item.get("job_id")
            profile_id = item.get("profile_id")
            rank = item.get("rank")

            if not job_id or not profile_id or rank is None:
                errors.append({"error": "job_id, profile_id, and rank are required", "data": item})
                continue

            try:
                ranking = JobRanking.objects.get(job_id=job_id, profile_id=profile_id)
                ranking.rank = rank
                ranking.save(update_fields=["rank"])
                updated += 1
            except JobRanking.DoesNotExist:
                errors.append({"error": f"Ranking not found for job={job_id} profile={profile_id}"})
            except Exception as e:
                errors.append({"error": str(e)})

        return Response(
            {"updated": updated, "errors": errors},
            status=status.HTTP_200_OK,
        )

from django.contrib.auth import authenticate, login, logout
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny


class AuthMeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            return Response({
                "authenticated": True,
                "username": request.user.username,
                "is_staff": request.user.is_staff,
            })
        return Response({"authenticated": False})


class AuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        if not username or not password:
            return Response({"error": "Username and password required."}, status=400)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "Invalid credentials."}, status=401)
        login(request, user)
        return Response({
            "authenticated": True,
            "username": user.username,
            "is_staff": user.is_staff,
        })


class AuthLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"authenticated": False})


class SettingsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from config import (
            get_apify_api_token, get_openai_model, get_openai_base_url,
            get_openai_api_keys,
        )
        return Response({
            "OPENAI_BASE_URL": get_openai_base_url() or "https://api.openai.com/v1",
            "OPENAI_MODEL": get_openai_model() or "gpt-4o-mini",
            "APIFY_API_TOKEN": get_apify_api_token() or "",
            "OPENAI_API_KEYS": get_openai_api_keys() or [],
        })

    def post(self, request):
        data = request.data
        api_keys = data.get("OPENAI_API_KEYS")
        if isinstance(api_keys, list):
            api_keys_str = ",".join([k.strip() for k in api_keys if k.strip()])
        else:
            api_keys_str = api_keys

        keys_to_update = {
            "OPENAI_BASE_URL": data.get("OPENAI_BASE_URL"),
            "OPENAI_MODEL": data.get("OPENAI_MODEL"),
            "APIFY_API_TOKEN": data.get("APIFY_API_TOKEN"),
            "OPENAI_API_KEYS": api_keys_str,
        }

        valid_keys = {k: str(v) for k, v in keys_to_update.items() if v is not None}

        if valid_keys:
            from config import set_dynamic_settings
            success = set_dynamic_settings(valid_keys)
            if not success:
                return Response({"status": "error", "message": "Failed to save settings to Redis."}, status=500)

        return Response({"status": "success", "message": "Settings updated successfully."})
