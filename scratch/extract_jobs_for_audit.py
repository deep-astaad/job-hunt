"""
Run inside jobhunt-django container to extract ranked jobs + rankings as JSON.
docker exec jobhunt-django python /tmp/extract_jobs_for_audit.py > /tmp/jobs_audit.json
"""
import sys
import os
import django
import json

sys.path.insert(0, "/app/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "job_hunt.settings")
# Disable import of config.py validators - settings only needs DB+secret
django.setup()

from jobs.models import Job, JobRanking

jobs_qs = Job.objects.filter(is_formatted=True).prefetch_related("rankings").order_by("-id")[:500]

out = []
for job in jobs_qs:
    rankings = list(job.rankings.values(
        "profile_id", "match_tier", "llm_tier", "rank", "jd_summary",
    ))
    out.append({
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "location": getattr(job, "location", ""),
        "region": getattr(job, "region", ""),
        "country": getattr(job, "country", ""),
        "is_remote": getattr(job, "is_remote", False),
        "description": (job.description or "")[:3000],
        "tech_stack": job.tech_stack or [],
        "required_experience": getattr(job, "required_experience", ""),
        "salary": getattr(job, "salary", ""),
        "salary_yen": getattr(job, "salary_yen", None),
        "language": getattr(job, "language", ""),
        "is_ranked": job.is_ranked,
        "rankings": rankings,
    })

json.dump(out, sys.stdout, default=str, ensure_ascii=False, indent=2)
sys.stderr.write(f"\nExtracted {len(out)} jobs\n")
