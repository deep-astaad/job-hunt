import hashlib

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count
from .models import Job, JobRanking
from .serializers import (
    JobSerializer,
    JobListSerializer,
    JobRankingSerializer,
)


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    filterset_fields = ["source", "is_active", "language", "company", "updated_at"]
    search_fields = ["title", "company", "description"]
    ordering_fields = ["scraped_at", "company", "title"]

    def get_serializer_class(self):
        if self.action == "list":
            return JobListSerializer
        return JobSerializer

    @action(detail=False, methods=["post"])
    def bulk_create(self, request):
        jobs_data = request.data if isinstance(request.data, list) else request.data.get("jobs", [])
        created, updated = 0, 0
        errors = []

        for job_data in jobs_data:
            url = job_data.get("url")
            if not url:
                errors.append({"error": "url is required", "data": job_data})
                continue

            url_hash = hashlib.sha256(url.encode()).hexdigest()

            try:
                obj, was_created = Job.objects.update_or_create(
                    url_hash=url_hash,
                    defaults={
                        "url": url,
                        "title": job_data.get("title", "Unknown"),
                        "company": job_data.get("company", "Unknown"),
                        "source": job_data.get("source", "custom"),
                        "salary": job_data.get("salary", ""),
                        "description": job_data.get("description", ""),
                        "full_description": job_data.get("full_description", ""),
                        "tech_stack": job_data.get("tech_stack"),
                        "language": job_data.get("language"),
                        "experience_required": job_data.get("experience_required", ""),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append({"error": str(e), "url": url})

        return Response(
            {"created": created, "updated": updated, "errors": errors},
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
            "by_source": by_source,
            "by_tier": by_tier,
        })


class JobRankingViewSet(viewsets.ModelViewSet):
    queryset = JobRanking.objects.select_related("job").all()
    serializer_class = JobRankingSerializer
    filterset_fields = ["profile_id", "match_tier"]
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
                obj, was_created = JobRanking.objects.update_or_create(
                    job=job,
                    profile_id=profile_id,
                    defaults={
                        "profile_title": rank_data.get("profile_title", ""),
                        "match_tier": rank_data.get("match_tier", "C"),
                        "rank": rank_data.get("rank", 0),
                        "jd_summary": rank_data.get("jd_summary", ""),
                    },
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
