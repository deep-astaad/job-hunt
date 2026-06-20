import hashlib

from django.db import models

from .parsers import (
    parse_salary_to_yen,
    required_jlpt_level,
    parse_location_region as _region_for_text,
    detect_remote_text as _detect_remote_text,
)


class Job(models.Model):
    SOURCE_CHOICES = [
        ("indeed", "Indeed"),
        ("linkedin", "LinkedIn"),
        ("japan_dev", "Japan Dev"),
        ("tokyo_dev", "Tokyo Dev"),
        ("daijob", "Daijob"),
        ("gaijinpot", "GaijinPot"),
        ("careercross", "CareerCross"),
        ("green", "Green"),
        ("wantedly", "Wantedly"),
        # Legacy slugs already present in production data. Keep them accepted so
        # PATCH/update paths do not reject rows before a data cleanup normalizes
        # them to japan_dev/tokyo_dev.
        ("japan-dev", "Japan Dev (legacy)"),
        ("tokyodev", "TokyoDev (legacy)"),
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
    salary_yen = models.PositiveIntegerField(null=True, blank=True)
    jlpt_level = models.PositiveSmallIntegerField(null=True, blank=True)  # 1=N1 (hardest) .. 5=N5
    description = models.TextField(blank=True, default="")
    full_description = models.TextField(blank=True, default="")
    tech_stack = models.JSONField(null=True, blank=True)
    raw_data = models.JSONField(null=True, blank=True)

    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, null=True, blank=True)
    experience_required = models.CharField(max_length=100, blank=True, default="")

    # Location: free-text as scraped, plus derived region/country for filtering.
    location = models.CharField(max_length=300, blank=True, default="")
    country = models.CharField(max_length=80, blank=True, default="", db_index=True)
    region = models.CharField(max_length=80, blank=True, default="", db_index=True)
    is_remote = models.BooleanField(default=False, db_index=True)

    is_active = models.BooleanField(default=True)
    is_formatted = models.BooleanField(default=False, db_index=True)
    is_ranked = models.BooleanField(default=False, db_index=True)
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
            models.Index(fields=["is_ranked"]),
        ]

    def save(self, *args, **kwargs):
        if not self.is_formatted:
            self.is_ranked = False
        # Derive structured fields from the free-text inputs so analytics can
        # rely on them instead of re-parsing at read time.
        self.salary_yen = parse_salary_to_yen(self.salary)
        text = f"{self.title} {self.description} {self.full_description}"
        level = required_jlpt_level(text)
        if level is None and (self.language or "").upper() == "JP":
            level = 2  # JP-required but no explicit level -> assume business (N2)
        self.jlpt_level = level

        # Derive region/country/remoteness from the location/description when the
        # caller didn't supply them, so location filtering works on legacy rows too.
        self._derive_location_fields()

        super().save(*args, **kwargs)

    def _derive_location_fields(self):
        loc_text = " ".join(filter(None, [self.location, self.title, self.description]))
        if not (self.region and self.country):
            region, country, _city = _region_for_text(loc_text)
            if not self.region and region:
                self.region = region
            if not self.country and country:
                self.country = country
        if not self.is_remote:
            self.is_remote = _detect_remote_text(
                " ".join(filter(None, [self.location, self.title, self.description, self.full_description]))
            )

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
    # Raw tier the LLM assigned, before hard-rule downgrades (e.g. Japanese / over-experience).
    llm_tier = models.CharField(max_length=2, choices=TIER_CHOICES, null=True, blank=True)
    # Tier from the deterministic matching engine (matching.compute_match), pre-blend.
    deterministic_tier = models.CharField(max_length=2, choices=TIER_CHOICES, null=True, blank=True)
    # Final blended numeric match score 0..100 (higher = better) for intra-tier sorting.
    match_score = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    # Per-dimension diagnostics from the matching engine (skill/title/experience/...).
    signals = models.JSONField(null=True, blank=True)
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.job.is_ranked:
            self.job.is_ranked = True
            self.job.save(update_fields=["is_ranked"])

    def __str__(self):
        return f"[{self.match_tier}] #{self.rank} {self.job.title}"
