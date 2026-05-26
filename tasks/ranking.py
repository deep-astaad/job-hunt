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





@app.task(
    bind=True,
    name='tasks.ranking.rank_job_multi_profile',
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=180,
)
def rank_job_multi_profile(self, formatted_job_data, profiles, pipeline_run_id=None, job_id=None):
    """Rank a single formatted job against ALL profiles in one GPT call."""
    effective_job_id = job_id or (formatted_job_data.get("id") if isinstance(formatted_job_data, dict) else None)

    if not formatted_job_data or not isinstance(formatted_job_data, dict):
        logger.warning("rank_skipped_no_job_data")
        _check_and_trigger_discord(pipeline_run_id, effective_job_id)
        return {"status": "skipped", "reason": "no_job_data"}

    if not effective_job_id:
        logger.warning("rank_skipped_no_job_id")
        _check_and_trigger_discord(pipeline_run_id, None)
        return {"status": "skipped", "reason": "no_job_id"}

    ranker = JobRankerAI()
    system_prompt = ranker._read_file("prompts/ranker.txt")

    for profile in profiles:
        profile["experience_years"] = ranker._parse_experience_years(
            profile.get("experience", "")
        )

    try:
        import os
        import time
        if os.getenv("MOCK_LLM") == "1":
            time.sleep(1)  # Simulate API latency
            json_text = json.dumps({
                "rankings": [
                    {
                        "profile_id": p["id"],
                        "match_tier": "A",
                        "jd_summary": "Dummy summary for " + p["id"]
                    } for p in profiles
                ]
            })
        else:
            json_text = _rank_single_job_multi_profile(
                ranker, formatted_job_data, profiles, system_prompt
            )
        rankings = _parse_rankings_json(json_text, profiles)
        rankings = _apply_hard_rules_multi(rankings, formatted_job_data)

        if rankings:
            _persist_rankings(effective_job_id, rankings)
            
    except (openai.RateLimitError, openai.APIError, openai.APITimeoutError) as exc:
        if os.getenv("MOCK_LLM") == "1":
            rankings = []
        else:
            logger.warning("rank_gpt_retry", extra={
                "job_id": effective_job_id, "attempt": self.request.retries, "error": str(exc),
            })
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    except Exception as exc:
        logger.error("rank_gpt_fatal", extra={"job_id": effective_job_id, "error": str(exc)})
        _check_and_trigger_discord(pipeline_run_id, effective_job_id)
        return {"status": "error", "job_id": effective_job_id}

    _check_and_trigger_discord(pipeline_run_id, effective_job_id)
    return {"status": "done", "job_id": effective_job_id, "ranked_profiles": len(rankings) if 'rankings' in locals() else 0}

def _check_and_trigger_discord(pipeline_run_id, job_id=None):
    """Remove job from Redis in-flight set, and trigger Discord if pipeline is fully complete."""
    if not pipeline_run_id:
        return

    import redis
    from config import CELERY_BROKER_URL
    from tasks.pipeline import send_discord_summary
    
    try:
        r = redis.Redis.from_url(CELERY_BROKER_URL)
        
        in_flight_key = f"pipeline:{pipeline_run_id}:in_flight"
        active_key = f"pipeline:{pipeline_run_id}:active_actors"
        dispatched_key = f"pipeline:{pipeline_run_id}:dispatched_at"
        summary_sent_key = f"pipeline:{pipeline_run_id}:summary_sent"
        
        removed = 0
        if job_id:
            removed = r.srem(in_flight_key, job_id)
            r.hdel(dispatched_key, job_id)
            
        # Only check completion if we actually removed the job or no job_id was provided
        if not job_id or removed == 1:
            active = int(r.get(active_key) or 0)
            in_flight_count = r.scard(in_flight_key)
            
            if active <= 0 and in_flight_count <= 0:
                if r.set(summary_sent_key, "1", nx=True, ex=86400):
                    send_discord_summary.delay(pipeline_run_id)
                # Cleanup redis keys safely
                r.delete(active_key)
                r.delete(in_flight_key)
                r.delete(dispatched_key)
    except Exception as exc:
        logger.error("redis_in_flight_removal_failed", extra={"pipeline_run_id": pipeline_run_id, "error": str(exc)})
