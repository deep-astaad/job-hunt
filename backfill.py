"""Backfill unformatted/unranked jobs.

Run inside the Celery worker container:
  docker compose exec celery-worker python backfill.py
"""
import json
import logging
import time
import requests
from persistence import JobFormatter, DjangoPersistence, normalize_url
from ranker import JobRankerAI
from outputs import ExportHandler
from config import DJANGO_API_URL, get_openai_model

logger = logging.getLogger(__name__)

GPT_DELAY = 1.5  # seconds between GPT calls to avoid rate limits


def fetch_all_unformatted():
    """Fetch all unformatted jobs (not just today's)."""
    url = f"{DJANGO_API_URL}/api/jobs/?is_formatted=false&page_size=100"
    all_jobs = []
    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_jobs.extend(data.get("results", []))
        url = data.get("next")
    return all_jobs


def fetch_all_unranked():
    """Fetch all formatted jobs that have no rankings."""
    url = f"{DJANGO_API_URL}/api/jobs/?is_formatted=true&page_size=100"
    all_jobs = []
    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for job in data.get("results", []):
            if not job.get("rankings"):
                all_jobs.append(job)
        url = data.get("next")
    return all_jobs


def format_jobs(jobs):
    """Format unformatted jobs via GPT and update in DB."""
    if not jobs:
        print("No unformatted jobs to process.")
        return 0

    formatter = JobFormatter()
    persister = DjangoPersistence()
    formatted = 0

    print(f"\nFormatting {len(jobs)} jobs via GPT...")
    for i, job in enumerate(jobs):
        raw_data = job.get("raw_data")
        input_json = raw_data or job
        try:
            result = formatter.format_job(input_json)
            result.setdefault("title", job.get("title", "Unknown"))
            result.setdefault("company", job.get("company", "Unknown"))
            result.setdefault("url", job.get("url", ""))
            result.setdefault("source", job.get("source", "custom"))
            result.setdefault("salary", "")
            result.setdefault("description", "")
            result.setdefault("full_description", "")
            result.setdefault("tech_stack", [])
            result.setdefault("language", "EN")
            result.setdefault("experience_required", "")
            if raw_data:
                result["raw_data"] = raw_data
            result["is_formatted"] = True
            persister.update_job(job["id"], result)
            formatted += 1
            print(f"  [{i+1}/{len(jobs)}] Formatted: {job.get('title', '?')[:50]}")
        except Exception as e:
            print(f"  [{i+1}/{len(jobs)}] Failed: {job.get('title', '?')[:50]} — {e}")
        time.sleep(GPT_DELAY)

    print(f"Formatted {formatted}/{len(jobs)} jobs.")
    return formatted


def rank_jobs(jobs, profiles, system_prompt):
    """Rank jobs against each profile and persist rankings."""
    if not jobs:
        print("No jobs to rank.")
        return 0

    persister = DjangoPersistence()
    ranked = 0

    print(f"\nRanking {len(jobs)} jobs against {len(profiles)} profiles...")
    for i, job in enumerate(jobs):
        for profile in profiles:
            pid = profile.get("id", "unknown")
            try:
                ranker = JobRankerAI()

                title_company = f"{job.get('title', '?')} @ {job.get('company', '?')}"
                salary = job.get("salary", "") or ""
                exp = job.get("experience_required", "") or ""
                lang = job.get("language", "") or ""
                summary = (job.get("description", "") or "")[:200]
                url = job.get("url", "")

                header = "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |"
                separator = "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"
                row = f"| 1 | ? | {title_company} | {salary} | {exp} | {lang} | {summary} | [{title_company[:30]}]({url}) |"
                single_job_table = f"{header}\n{separator}\n{row}"

                user_content = (
                    f"CANDIDATE PROFILE:\n{json.dumps(profile, indent=2)}\n\n"
                    f"Rank this single job and return the table with the Match Tier filled in.\n\n"
                    f"{single_job_table}"
                )

                response = ranker.client.chat.completions.create(
                    model=get_openai_model(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.2,
                )
                table = response.choices[0].message.content.strip()
                if table.startswith("```"):
                    table = table.split("\n", 1)[1]
                if table.endswith("```"):
                    table = table.rsplit("```", 1)[0]

                rows = ranker._parse_ranking_table(table.strip())
                rows = ranker._apply_hard_rules(rows)

                if rows:
                    tier = rows[0][1] if len(rows[0]) > 1 else "C"
                    jd_summary = rows[0][6] if len(rows[0]) > 6 else ""
                    requests.post(
                        f"{DJANGO_API_URL}/api/rankings/bulk_create/",
                        json=[{
                            "job_id": job["id"],
                            "profile_id": pid,
                            "profile_title": profile.get("title", pid),
                            "match_tier": tier.upper(),
                            "rank": 0,
                            "jd_summary": jd_summary,
                        }],
                        timeout=10,
                    )
                    ranked += 1
                    print(f"  [{i+1}/{len(jobs)}] {pid}: {tier.upper()} — {job.get('title', '?')[:40]}")
            except Exception as e:
                print(f"  [{i+1}/{len(jobs)}] {pid} failed: {job.get('title', '?')[:40]} — {e}")
            time.sleep(GPT_DELAY)

    print(f"Ranked {ranked} job-profile pairs.")
    return ranked


if __name__ == "__main__":
    print("=" * 50)
    print("BACKFILL: Format + Rank + Discord Alert")
    print("=" * 50)

    # Step 1: Format unformatted jobs
    unformatted = fetch_all_unformatted()
    print(f"Found {len(unformatted)} unformatted jobs.")
    format_jobs(unformatted)

    # Step 2: Fetch all formatted jobs and rank unranked ones
    all_formatted = []
    url = f"{DJANGO_API_URL}/api/jobs/?is_formatted=true&page_size=100"
    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_formatted.extend(data.get("results", []))
        url = data.get("next")

    unranked = [j for j in all_formatted if not j.get("rankings")]
    print(f"Found {len(unranked)} unranked jobs out of {len(all_formatted)} formatted.")

    ranker_instance = JobRankerAI()
    profiles = ranker_instance._load_json("user-profiles.json")
    system_prompt = ranker_instance._read_file("prompts/ranker.txt")
    rank_jobs(unranked, profiles, system_prompt)

    # Step 3: Send Discord summary
    print("\nSending Discord summary...")
    ExportHandler.post_tiered_jobs_from_api()

    print("\n" + "=" * 50)
    print("BACKFILL COMPLETE")
    print("=" * 50)
