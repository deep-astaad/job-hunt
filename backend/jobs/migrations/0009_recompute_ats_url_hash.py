"""Recompute url_hash for rows on the newly-allowlisted ATS domains.

normalize_url now keeps the per-domain identity query param (e.g. Taleo `job`,
Jobvite `j`, SuccessFactors `jobId`, Workable `jid`, SmartRecruiters `job`).
Existing rows on those domains were hashed with the old "strip all params"
rule, so a re-scrape of the same posting would compute a *different* url_hash
and fork into a duplicate row, orphaning the original formatted/ranked one.

This migration recomputes url_hash for those rows using the new normalizer so
re-scrapes match the existing row in place. It is a no-op when no such rows
exist. Indeed (the only other allowlisted domain) is unchanged by the new
rule, so its rows are intentionally left alone.
"""
import hashlib

from django.db import migrations

_ATS_DOMAINS = (
    "taleo.net",
    "jobvite.com",
    "successfactors.com",
    "successfactors.eu",
    "workable.com",
    "smartrecruiters.com",
)


def recompute(apps, schema_editor):
    from jobs.parsers import normalize_url

    Job = apps.get_model("jobs", "Job")

    q = None
    from django.db.models import Q
    for d in _ATS_DOMAINS:
        clause = Q(url__icontains=d)
        q = clause if q is None else (q | clause)

    for job in Job.objects.filter(q).iterator():
        new_hash = hashlib.sha256(normalize_url(job.url).encode()).hexdigest()
        if new_hash == job.url_hash:
            continue
        # Collision-safe: never overwrite onto a hash another row already owns.
        if Job.objects.filter(url_hash=new_hash).exclude(pk=job.pk).exists():
            continue
        job.url_hash = new_hash
        job.save(update_fields=["url_hash"])


def noop_reverse(apps, schema_editor):
    # Hash recomputation is not reversible; leaving rows as-is is safe.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0008_job_country_job_is_remote_job_location_job_region_and_more"),
    ]

    operations = [
        migrations.RunPython(recompute, noop_reverse),
    ]
