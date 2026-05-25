import json
import logging
import re

import openai
import requests
from celery_app import app
from config import DJANGO_API_URL
from ranker import JobRankerAI

logger = logging.getLogger(__name__)


def _rank_single_job_multi_profile(ranker, job_data, profiles, system_prompt):
    """Send one job + all profiles to GPT in a single call. Returns markdown table."""
    title_company = f"{job_data.get('title', '?')} @ {job_data.get('company', '?')}"
    salary = job_data.get("salary", "") or ""
    exp = job_data.get("experience_required", "") or ""
    lang = job_data.get("language", "") or ""
    summary = (job_data.get("description", "") or "")[:200]
    url = job_data.get("url", "")

    user_content = (
        f"CANDIDATE PROFILES:\n{json.dumps(profiles, indent=2)}\n\n"
        f"JOB TO EVALUATE:\n"
        f"Title & Company: {title_company}\n"
        f"Salary Range: {salary}\n"
        f"Experience Required: {exp}\n"
        f"Language: {lang}\n"
        f"JD Summary: {summary}\n"
        f"URL: {url}\n\n"
        f"Rank this single job against EACH profile independently.\n"
        f"Return a JSON object containing the 'rankings' array as specified in the instructions."
    )

    response = ranker.client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        timeout=60,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content


def _parse_rankings_json(json_text, profiles):
    """Parse multi-profile ranking JSON. Returns list of ranking dicts."""
    try:
        data = json.loads(json_text)
        raw_rankings = data.get("rankings", [])
    except json.JSONDecodeError:
        return []

    profile_ids = {p["id"] for p in profiles}
    rankings = []

    for r in raw_rankings:
        pid = str(r.get("profile_id", "")).strip()
        tier = str(r.get("match_tier", "C")).strip().upper()
        summary = str(r.get("jd_summary", "")).strip()

        # Match profile_id (normalize whitespace/case)
        pid_clean = pid.lower().replace(" ", "_")
        matched_pid = next(
            (p for p in profile_ids if p.lower().replace(" ", "_") == pid_clean),
            pid,
        )

        rankings.append({
            "profile_id": matched_pid,
            "match_tier": tier,
            "jd_summary": summary,
        })

    # Fallback: if GPT garbled the Profile ID column but row count matches,
    # assume rows are in the same order as the profiles list
    if (
        rankings
        and len(rankings) == len(profiles)
        and not any(r["profile_id"] in profile_ids for r in rankings)
    ):
        for i, r in enumerate(rankings):
            r["profile_id"] = profiles[i]["id"]

    return rankings


def _apply_hard_rules_multi(rankings, job_data):
    """Override tier to F for jobs requiring Japanese or >4 years experience."""
    lang = (job_data.get("language", "") or "").lower()
    exp_text = (job_data.get("experience_required", "") or "").lower()

    is_jp_required = any(kw in lang for kw in ["jp", "japanese", "jlpt"])
    exp_match = re.search(r"(\d+)", exp_text)
    exp_years = int(exp_match.group(1)) if exp_match else None
    is_experienced = exp_years is not None and exp_years > 4

    if is_jp_required or is_experienced:
        for r in rankings:
            r["match_tier"] = "F"

    return rankings


def _persist_rankings(job_id, rankings):
    """POST rankings to Django API."""
    payload = []
    for r in rankings:
        payload.append({
            "job_id": job_id,
            "profile_id": r["profile_id"],
            "profile_title": r["profile_id"],
            "match_tier": r["match_tier"],
            "rank": 0,
            "jd_summary": r["jd_summary"],
        })

    try:
        resp = requests.post(
            f"{DJANGO_API_URL}/api/rankings/bulk_create/",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("ranking_persist_failed", extra={
            "job_id": job_id, "error": str(exc),
        })


def _batch_rank_jobs_for_profile(ranker, profile_rankings, profile, system_prompt):
    """Send all jobs for one profile to GPT for batch ranking. Returns ordered list."""
    header = "| Job ID | Match Tier | Job Title & Company | JD Summary |"
    separator = "|--------|------------|---------------------|------------|"

    rows = []
    for pr in profile_rankings:
        job = pr["job"]
        title_company = f"{job.get('title', '?')} @ {job.get('company', '?')}"
        summary = (pr.get("jd_summary", "") or "")[:150]
        rows.append(
            f"| {pr['job_id']} | {pr['match_tier']} | {title_company} | {summary} |"
        )

    table = f"{header}\n{separator}\n" + "\n".join(rows)

    user_content = (
        f"CANDIDATE PROFILE:\n{json.dumps(profile, indent=2)}\n\n"
        f"JOBS WITH PRE-ASSIGNED TIERS:\n{table}"
    )

    response = ranker.client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        timeout=120,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content


@app.task(
    bind=True,
    name='tasks.ranking.rank_jobs_by_profile',
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=1800,
)
def rank_jobs_by_profile(self):
    """Phase 2: batch-rank all today's jobs within each profile for proper ordering.

    Fetches today's ranked jobs, groups by profile_id, sends each group to GPT
    for ordering, then updates the rank field via API.
    """
    ranker = JobRankerAI()
    system_prompt = ranker._read_file("prompts/batch_ranker.txt")
    profiles = ranker._load_json("user-profiles.json")
    profiles_by_id = {p["id"]: p for p in profiles}

    # Fetch today's jobs with ALL per-profile rankings
    try:
        resp = requests.get(
            f"{DJANGO_API_URL}/api/jobs/today-all-rankings/",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("results", [])
    except Exception as exc:
        logger.error("batch_rank_fetch_failed", extra={"error": str(exc)})
        return {"status": "error", "reason": "fetch_failed"}

    if not jobs:
        return {"status": "done", "ranked": 0}

    # Group by profile_id: each job has per-profile rankings
    by_profile = {}
    for job in jobs:
        for r in job.get("rankings", []):
            pid = r.get("profile_id", "")
            if pid not in by_profile:
                by_profile[pid] = []
            by_profile[pid].append({
                "job_id": job["id"],
                "match_tier": r.get("match_tier", "C"),
                "jd_summary": r.get("jd_summary", ""),
                "job": {
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                },
            })

    total_ranked = 0
    BATCH_SIZE = 50
    tier_sort = {t: i for i, t in enumerate(["S", "A", "B", "C", "F"])}

    for pid, job_rankings in by_profile.items():
        profile = profiles_by_id.get(pid)
        if not profile:
            logger.warning("batch_rank_unknown_profile", extra={"profile_id": pid})
            continue

        profile["experience_years"] = ranker._parse_experience_years(
            profile.get("experience", "")
        )

        # Chunk into batches to avoid GPT timeout on large payloads
        all_rank_updates = []
        chunks = [job_rankings[i:i+BATCH_SIZE] for i in range(0, len(job_rankings), BATCH_SIZE)]
        logger.info("batch_rank_chunks", extra={
            "profile_id": pid, "total_jobs": len(job_rankings), "chunks": len(chunks),
        })

        for chunk_idx, chunk in enumerate(chunks):
            try:
                response_text = _batch_rank_jobs_for_profile(
                    ranker, chunk, profile, system_prompt
                )
                if response_text.startswith("```"):
                    response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text.rsplit("```", 1)[0]
                response_text = response_text.strip()

                data = json.loads(response_text)
                ordered = data.get("rankings", [])
                if not isinstance(ordered, list):
                    logger.warning("batch_rank_bad_response", extra={
                        "profile_id": pid, "chunk": chunk_idx,
                    })
                    continue

                for item in ordered:
                    if "job_id" in item and "rank" in item:
                        all_rank_updates.append({
                            "job_id": item["job_id"],
                            "profile_id": pid,
                            "rank": item["rank"],
                        })

            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("batch_rank_parse_failed", extra={
                    "profile_id": pid, "chunk": chunk_idx, "error": str(exc),
                })
            except (openai.RateLimitError, openai.APIError, openai.APITimeoutError) as exc:
                logger.warning("batch_rank_gpt_retry", extra={
                    "profile_id": pid, "attempt": self.request.retries, "error": str(exc),
                })
                raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
            except Exception as exc:
                logger.error("batch_rank_fatal", extra={
                    "profile_id": pid, "chunk": chunk_idx, "error": str(exc),
                })

        # Re-number ranks across all chunks: sort by tier priority, then original rank
        if all_rank_updates:
            # Build tier lookup from the original job_rankings
            tier_by_job = {r["job_id"]: r.get("match_tier", "F") for r in job_rankings}
            all_rank_updates.sort(
                key=lambda x: (
                    tier_sort.get(tier_by_job.get(x["job_id"], "F"), 99),
                    x["rank"],
                )
            )
            for i, item in enumerate(all_rank_updates, 1):
                item["rank"] = i

            _update_ranks(all_rank_updates)
            total_ranked += len(all_rank_updates)

    return {"status": "done", "ranked": total_ranked}


def _update_ranks(rank_updates):
    """POST rank updates to Django API in chunks to avoid timeout."""
    CHUNK_SIZE = 100
    for i in range(0, len(rank_updates), CHUNK_SIZE):
        chunk = rank_updates[i:i+CHUNK_SIZE]
        try:
            resp = requests.post(
                f"{DJANGO_API_URL}/api/rankings/update_ranks/",
                json=chunk,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("rank_update_failed", extra={
                "error": str(exc), "chunk_start": i, "chunk_size": len(chunk),
            })


@app.task(
    bind=True,
    name='tasks.ranking.rank_job_multi_profile',
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=180,
)
def rank_job_multi_profile(self, formatted_job_data, profiles, pipeline_run_id=None):
    """Rank a single formatted job against ALL profiles in one GPT call."""
    if not formatted_job_data or not isinstance(formatted_job_data, dict):
        logger.warning("rank_skipped_no_job_data")
        _check_and_trigger_discord(pipeline_run_id)
        return {"status": "skipped", "reason": "no_job_data"}

    job_id = formatted_job_data.get("id")
    if not job_id:
        logger.warning("rank_skipped_no_job_id")
        _check_and_trigger_discord(pipeline_run_id)
        return {"status": "skipped", "reason": "no_job_id"}

    ranker = JobRankerAI()
    system_prompt = ranker._read_file("prompts/ranker.txt")

    for profile in profiles:
        profile["experience_years"] = ranker._parse_experience_years(
            profile.get("experience", "")
        )

    try:
        json_text = _rank_single_job_multi_profile(
            ranker, formatted_job_data, profiles, system_prompt
        )
        rankings = _parse_rankings_json(json_text, profiles)
        rankings = _apply_hard_rules_multi(rankings, formatted_job_data)

        if rankings:
            _persist_rankings(job_id, rankings)
            
    except (openai.RateLimitError, openai.APIError, openai.APITimeoutError) as exc:
        logger.warning("rank_gpt_retry", extra={
            "job_id": job_id, "attempt": self.request.retries, "error": str(exc),
        })
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    except Exception as exc:
        logger.error("rank_gpt_fatal", extra={"job_id": job_id, "error": str(exc)})
        _check_and_trigger_discord(pipeline_run_id)
        return {"status": "error", "job_id": job_id}

    _check_and_trigger_discord(pipeline_run_id)
    return {"status": "done", "job_id": job_id, "ranked_profiles": len(rankings) if 'rankings' in locals() else 0}

def _check_and_trigger_discord(pipeline_run_id):
    """Decrement Redis pending counter and trigger Discord if pipeline is fully complete."""
    if not pipeline_run_id:
        return

    import redis
    from config import CELERY_BROKER_URL
    from tasks.pipeline import send_discord_summary
    
    try:
        r = redis.Redis.from_url(CELERY_BROKER_URL)
        pending = r.decr(f"pipeline:{pipeline_run_id}:pending_jobs")
        active = int(r.get(f"pipeline:{pipeline_run_id}:active_actors") or 0)
        
        if pending <= 0 and active <= 0:
            send_discord_summary.delay(pipeline_run_id)
            # Cleanup redis keys safely
            r.delete(f"pipeline:{pipeline_run_id}:pending_jobs")
            r.delete(f"pipeline:{pipeline_run_id}:active_actors")
    except Exception as exc:
        logger.error("redis_decrement_failed", extra={"pipeline_run_id": pipeline_run_id, "error": str(exc)})
