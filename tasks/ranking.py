import json
import logging
import re

import openai
import requests
from celery_app import app
from config import DJANGO_API_URL, get_openai_model
from ranker import JobRankerAI

logger = logging.getLogger(__name__)


# Max chars of job description sent to the LLM. The old code truncated to 200,
# which starved the model of almost all signal; the full JD is the richest input.
_MAX_JD_CHARS = 4000


def _rank_single_job_multi_profile(ranker, job_data, profiles, system_prompt):
    """Send one job + all profiles to GPT in a single call. Returns JSON text.

    Unlike the original implementation this passes the FULL job context (full
    description, tech stack, location) instead of a 200-char teaser, so the
    LLM's tier reflects the actual role.
    """
    title_company = f"{job_data.get('title', '?')} @ {job_data.get('company', '?')}"
    salary = job_data.get("salary", "") or ""
    exp = job_data.get("experience_required", "") or ""
    lang = job_data.get("language", "") or ""
    location = job_data.get("location", "") or ""
    tech_stack = job_data.get("tech_stack") or []
    # Prefer the full description; fall back to the short one.
    description = (job_data.get("full_description") or job_data.get("description") or "")[:_MAX_JD_CHARS]
    url = job_data.get("url", "")

    # Only send the fields the model needs (keeps prompt small + cheap for local models).
    slim_profiles = [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "experience": p.get("experience"),
            "core_skills": p.get("core_skills", []),
            "preferences": p.get("preferences", ""),
        }
        for p in profiles
    ]

    user_content = (
        f"CANDIDATE PROFILES:\n{json.dumps(slim_profiles, indent=2)}\n\n"
        f"JOB TO EVALUATE:\n"
        f"Title & Company: {title_company}\n"
        f"Location: {location}\n"
        f"Salary Range: {salary}\n"
        f"Experience Required: {exp}\n"
        f"Language: {lang}\n"
        f"Tech Stack: {', '.join(str(t) for t in tech_stack) if tech_stack else 'Unknown'}\n"
        f"Full Job Description:\n{description}\n"
        f"URL: {url}\n\n"
        f"Rank this single job against EACH profile independently based on genuine "
        f"role/skill fit.\n"
        f"Return a JSON object containing the 'rankings' array as specified in the instructions."
    )

    from llm import chat_completion
    return chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        timeout=120,
        response_format={"type": "json_object"},
    )


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


# Representative numeric score for a tier — used only to derive match_score/rank
# until Task 3 wires the LLM's own 0-100 match_score straight through. Mirrors
# the mapping the old deterministic engine (matching.TIER_SCORE) used.
TIER_SCORE = {"S": 92, "A": 74, "B": 56, "C": 38, "F": 8}


def _rankings_from_llm(llm_rankings, profiles):
    """Map parsed LLM rankings straight to ranking dicts — no deterministic engine.

    Issue #125: the deterministic matching engine (matching.py, compute_match,
    blend_with_llm) is deleted. The LLM's tier is now authoritative: match_tier
    and llm_tier are both the LLM's tier verbatim, deterministic_tier/signals are
    NULL (the DB columns stay for historical rows), and match_score/rank are
    derived from TIER_SCORE as a placeholder until Task 3 has the LLM return its
    own 0-100 match_score. Returns one ranking dict per profile.
    """
    llm_by_pid = {r.get("profile_id"): r for r in llm_rankings}

    out = []
    for profile in profiles:
        pid = profile.get("id")
        llm = llm_by_pid.get(pid, {})
        tier = str(llm.get("match_tier") or "C").strip().upper()
        if tier not in TIER_SCORE:
            tier = "C"
        summary = llm.get("jd_summary", "")
        score = TIER_SCORE[tier]

        out.append({
            "profile_id": pid,
            "match_tier": tier,
            "llm_tier": tier,
            "deterministic_tier": None,
            "match_score": score,
            "signals": None,
            "jd_summary": summary,
            # Lower rank sorts first; derive from score so best matches lead.
            "rank": max(0, 100 - score),
        })
    return out


def _persist_rankings(job_id, rankings):
    """POST rankings to Django API."""
    payload = []
    for r in rankings:
        payload.append({
            "job_id": job_id,
            "profile_id": r["profile_id"],
            "profile_title": r["profile_id"],
            "match_tier": r["match_tier"],
            "llm_tier": r.get("llm_tier"),
            "deterministic_tier": r.get("deterministic_tier"),
            "match_score": r.get("match_score"),
            "signals": r.get("signals"),
            "rank": r.get("rank", 0),
            "jd_summary": r["jd_summary"],
        })

    resp = requests.post(
        f"{DJANGO_API_URL}/api/rankings/bulk_create/",
        json=payload,
        timeout=10,
    )
    try:
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("ranking_persist_failed", extra={
            "job_id": job_id,
            "status_code": getattr(resp, "status_code", None),
            "response_body": getattr(resp, "text", "")[:1000],
            "error": str(exc),
        })
        raise


def _retry_or_release(self, exc, pipeline_run_id, job_id):
    if self.request.retries >= self.max_retries:
        _check_and_trigger_discord(pipeline_run_id, job_id)
        raise exc
    raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))





@app.task(
    bind=True,
    name='tasks.ranking.rank_job_multi_profile',
    max_retries=5,
    default_retry_delay=30,
    soft_time_limit=300,
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
    # Never mutate the shared (cached) profile dicts here — the worker pool is
    # --pool=threads and concurrent tasks share the same list, causing a data race.
    rankings = []  # initialize so the finally/return path always has it defined

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
        llm_rankings = _parse_rankings_json(json_text, profiles)
        rankings = _rankings_from_llm(llm_rankings, profiles)

        if rankings:
            _persist_rankings(effective_job_id, rankings)
            
            # Send Discord notification for S/A ranked jobs immediately
            s_a_rankings = [r for r in rankings if r.get("match_tier") in ("S", "A")]
            if s_a_rankings:
                try:
                    from outputs import ExportHandler
                    ExportHandler.post_single_job_to_discord(formatted_job_data, s_a_rankings)
                except Exception as e:
                    logger.error("failed_single_discord_post", extra={"job_id": effective_job_id, "error": str(e)})
            
    except (openai.RateLimitError, openai.APIError, openai.APITimeoutError) as exc:
        if os.getenv("MOCK_LLM") == "1":
            rankings = []
        else:
            logger.warning("rank_gpt_retry", extra={
                "job_id": effective_job_id, "attempt": self.request.retries, "error": str(exc),
            })
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    except requests.RequestException as exc:
        logger.warning("rank_persist_retry", extra={
            "job_id": effective_job_id,
            "attempt": self.request.retries,
            "error": str(exc),
        })
        _retry_or_release(self, exc, pipeline_run_id, effective_job_id)
    except Exception as exc:
        logger.error("rank_gpt_fatal", extra={"job_id": effective_job_id, "error": str(exc)})
        _check_and_trigger_discord(pipeline_run_id, effective_job_id)
        raise

    _check_and_trigger_discord(pipeline_run_id, effective_job_id)
    return {"status": "done", "job_id": effective_job_id, "ranked_profiles": len(rankings)}

def _check_and_trigger_discord(pipeline_run_id, job_id=None):
    """Remove job from Redis in-flight set, and trigger Discord if pipeline is fully complete."""
    if job_id:
        _clear_processing_lock(job_id)

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


def _clear_processing_lock(job_id):
    try:
        import redis
        from config import CELERY_BROKER_URL
        redis.Redis.from_url(CELERY_BROKER_URL).delete(f"job_processing_lock:{job_id}")
    except Exception as exc:
        logger.error("job_processing_lock_release_failed", extra={
            "job_id": job_id,
            "error": str(exc),
        })
