import hashlib

from django.db import models


class Job(models.Model):
    SOURCE_CHOICES = [
        ("indeed", "Indeed"),
        ("linkedin", "LinkedIn"),
        ("japan_dev", "Japan Dev"),
        ("tokyo_dev", "Tokyo Dev"),
        ("daijob", "Daijob"),
        ("custom", "Custom/Other"),
    ]

    LANGUAGE_CHOICES = [
        ("EN", "English"),
        ("JP", "Japanese"),
        ("non-english", "Non-English"),
    ]

    title = models.CharField(max_length=500)
    company = models.CharField(max_length=300)
    url = models.TextField()
    url_hash = models.CharField(max_length=64, unique=True, db_index=True)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default="custom")

    salary = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    full_description = models.TextField(blank=True, default="")
    tech_stack = models.JSONField(null=True, blank=True)
    raw_data = models.JSONField(null=True, blank=True)

    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, null=True, blank=True)
    experience_required = models.CharField(max_length=100, blank=True, default="")

    is_active = models.BooleanField(default=True)
    is_formatted = models.BooleanField(default=False, db_index=True)
    alert_sent = models.BooleanField(default=False, db_index=True)

    scraped_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scraped_at"]
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["company"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_formatted"]),
        ]

    def __str__(self):
        return f"{self.title} @ {self.company}"


class JobRanking(models.Model):
    TIER_CHOICES = [
        ("S", "S Tier"),
        ("A", "A Tier"),
        ("B", "B Tier"),
        ("C", "C Tier"),
        ("F", "F Tier"),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="rankings")
    profile_id = models.CharField(max_length=100)
    profile_title = models.CharField(max_length=200, blank=True, default="")
    match_tier = models.CharField(max_length=2, choices=TIER_CHOICES)
    rank = models.PositiveIntegerField()
    jd_summary = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank"]
        unique_together = ["job", "profile_id"]
        indexes = [
            models.Index(fields=["profile_id"]),
            models.Index(fields=["match_tier"]),
        ]

    def __str__(self):
        return f"[{self.match_tier}] #{self.rank} {self.job.title}"
