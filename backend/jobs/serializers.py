from rest_framework import serializers
from .models import Job, JobRanking


class JobRankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobRanking
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class JobSerializer(serializers.ModelSerializer):
    rankings = JobRankingSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = "__all__"
        read_only_fields = ["id", "scraped_at", "updated_at"]


class JobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "url", "source", "salary",
            "language", "experience_required", "is_active", "scraped_at",
        ]
