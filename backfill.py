"""Backfill unformatted/unranked jobs.

Run inside the Celery worker container:
  docker compose exec celery-worker python backfill.py
"""
import json
import logging
import time
import requests
from persistence import JobFormatter, DjangoPersistence, normalize_url, detect_job_location
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
            from persistence import detect_job_language
            result.setdefault("title", job.get("title", "Unknown"))
            result.setdefault("company", job.get("company", "Unknown"))
            result.setdefault("url", job.get("url", ""))
            result.setdefault("source", job.get("source", "custom"))
            result.setdefault("salary", "")
            result.setdefault("description", "")
            result.setdefault("full_description", "")
            result.setdefault("tech_stack", [])
            result.setdefault("language", "EN")
            result["language"] = detect_job_language(result)
            result["location"] = detect_job_location(result, raw_data)
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

    ranked = 0

    # Reuse the live pipeline's ranking path so backfill stays consistent with it:
    # full-context LLM call + deterministic matching engine + blended score.
    from tasks.ranking import (
        _rank_single_job_multi_profile,
        _parse_rankings_json,
        _apply_matching_engine,
        _persist_rankings,
    )

    ranker = JobRankerAI()
    for profile in profiles:
        profile["experience_years"] = profile.get(
            "experience_years", ranker._parse_experience_years(profile.get("experience", ""))
        )

    print(f"\nRanking {len(jobs)} jobs against {len(profiles)} profiles (full-context + engine)...")
    for i, job in enumerate(jobs):
        try:
            json_text = _rank_single_job_multi_profile(ranker, job, profiles, system_prompt)
            llm_rankings = _parse_rankings_json(json_text, profiles)
            rankings = _apply_matching_engine(llm_rankings, job, profiles)
            if rankings:
                _persist_rankings(job["id"], rankings)
                ranked += len(rankings)
                tiers = ", ".join(f"{r['profile_id']}:{r['match_tier']}({r['match_score']})" for r in rankings)
                print(f"  [{i+1}/{len(jobs)}] {job.get('title', '?')[:40]} -> {tiers}")
        except Exception as e:
            print(f"  [{i+1}/{len(jobs)}] failed: {job.get('title', '?')[:40]} — {e}")
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
