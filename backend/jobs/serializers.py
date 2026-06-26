from rest_framework import serializers
from .models import Job, JobApplicationStatus, JobRanking


class UserAppliedStatusSerializerMixin(serializers.ModelSerializer):
    is_applied = serializers.SerializerMethodField()

    def get_is_applied(self, obj):
        annotated = getattr(obj, "user_is_applied", None)
        if annotated is not None:
            return bool(annotated)

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False

        return JobApplicationStatus.objects.filter(user=user, job=obj, is_applied=True).exists()


class JobRankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobRanking
        fields = "__all__"
        read_only_fields = ["id", "created_at", "llm_tier"]


class JobSerializer(UserAppliedStatusSerializerMixin):
    rankings = JobRankingSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = "__all__"
        read_only_fields = ["id", "url_hash", "scraped_at", "updated_at", "salary_yen", "jlpt_level"]


class JobListSerializer(UserAppliedStatusSerializerMixin):
    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source", "salary",
            "language", "experience_required", "is_active", "is_ranked", "scraped_at",
            "location", "region", "country", "is_remote", "is_applied",
        ]


class TodayRankedJobSerializer(UserAppliedStatusSerializerMixin):
    ranking = serializers.SerializerMethodField()
    matched_profiles = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source", "salary",
            "description", "language", "experience_required", "scraped_at",
            "location", "region", "country", "is_remote", "is_applied",
            "ranking", "matched_profiles",
        ]

    def get_ranking(self, obj):
        ranking = obj._primary_ranking
        return {
            "match_tier": ranking.match_tier,
            "rank": ranking.rank,
            "match_score": ranking.match_score,
            "jd_summary": ranking.jd_summary,
            "created_at": ranking.created_at,
        }

    def get_matched_profiles(self, obj):
        return [
            {"profile_id": r.profile_id, "profile_title": r.profile_title}
            for r in obj._matched_rankings
        ]


class JobInlineSerializer(UserAppliedStatusSerializerMixin):
    """Compact job representation embedded inside a browse ranking row."""

    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source",
            "salary", "salary_yen", "language", "experience_required",
            "description", "tech_stack", "scraped_at", "jlpt_level",
            "location", "region", "country", "is_remote", "is_applied",
        ]


class JobRankingBrowseSerializer(serializers.ModelSerializer):
    """Ranking row with the full job object nested — used by BrowseView."""

    job = serializers.SerializerMethodField()

    def get_job(self, obj):
        job = obj.job
        if hasattr(obj, "user_is_applied"):
            job.user_is_applied = obj.user_is_applied
        return JobInlineSerializer(job, context=self.context).data

    class Meta:
        model = JobRanking
        fields = [
            "id", "profile_id", "match_tier", "llm_tier",
            "rank", "match_score", "jd_summary", "created_at", "job",
        ]
