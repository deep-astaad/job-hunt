from rest_framework import serializers
from .models import Job, JobRanking


class JobRankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobRanking
        fields = "__all__"
        read_only_fields = ["id", "created_at", "llm_tier"]


class JobSerializer(serializers.ModelSerializer):
    rankings = JobRankingSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = "__all__"
        read_only_fields = ["id", "url_hash", "scraped_at", "updated_at", "salary_yen", "jlpt_level"]


class JobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source", "salary",
            "language", "experience_required", "is_active", "is_ranked", "scraped_at",
        ]


class TodayRankedJobSerializer(serializers.ModelSerializer):
    ranking = serializers.SerializerMethodField()
    matched_profiles = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source", "salary",
            "description", "language", "experience_required", "scraped_at",
            "ranking", "matched_profiles",
        ]

    def get_ranking(self, obj):
        ranking = obj._primary_ranking
        return {
            "match_tier": ranking.match_tier,
            "rank": ranking.rank,
            "jd_summary": ranking.jd_summary,
            "created_at": ranking.created_at,
        }

    def get_matched_profiles(self, obj):
        return [
            {"profile_id": r.profile_id, "profile_title": r.profile_title}
            for r in obj._matched_rankings
        ]
