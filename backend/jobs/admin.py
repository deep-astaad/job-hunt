from django.contrib import admin
from .models import Job, JobRanking


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "source", "language", "is_active", "scraped_at"]
    list_filter = ["source", "language", "is_active"]
    search_fields = ["title", "company"]
    readonly_fields = ["scraped_at", "updated_at"]


@admin.register(JobRanking)
class JobRankingAdmin(admin.ModelAdmin):
    list_display = ["rank", "match_tier", "job", "profile_id", "created_at"]
    list_filter = ["match_tier", "profile_id"]
    search_fields = ["job__title", "job__company"]
