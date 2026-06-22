import logging
import time
import uuid
from datetime import datetime
from celery import chain
from celery_app import app
from persistence import DjangoPersistence, normalize_url
from config import get_apify_api_token, CELERY_BROKER_URL
import redis
import requests as req
from apify_client import ApifyClient
from apify_client._errors import ApifyApiError
from requests.exceptions import RequestException

from local_scrapers import (
    scrape_japan_dev,
    scrape_tokyo_dev,
    scrape_gaijinpot,
    scrape_careercross,
    scrape_green,
    scrape_daijob,
    scrape_wantedly
)

logger = logging.getLogger(__name__)

POLL_BATCH_SIZE = 1000


def _merge_job_maps(target, source):
    for url, info in (source or {}).items():
        if info:
            target[url] = info


def _save_jobs_with_fallback(persister, batch_jobs):
    """Persist scraper stubs and return the normalized-url job map.

    Bulk API calls can fail client-side after Django has already committed some
    rows. Falling back per job lets the caller recover ids for committed rows and
    dispatch them instead of leaving fresh jobs unformatted.
    """
    jobs_by_url = {}
    if not batch_jobs:
        return jobs_by_url

    expected_urls = [
        normalize_url(job["url"])
        for job in batch_jobs
        if job.get("url")
    ]

    try:
        result = persister.save_jobs(batch_jobs)
        _merge_job_maps(jobs_by_url, result.get("jobs", {}))
    except Exception as exc:
        logger.error("batch_save_failed", extra={
            "batch_size": len(batch_jobs),
            "error": str(exc),
        })

    missing_jobs = [
        job for job in batch_jobs
        if job.get("url") and normalize_url(job["url"]) not in jobs_by_url
    ]
    if not missing_jobs:
        return jobs_by_url

    logger.warning("batch_save_fallback_started", extra={
        "missing_count": len(missing_jobs),
        "batch_size": len(batch_jobs),
    })
    for job in missing_jobs:
        url = job.get("url")
        norm_url = normalize_url(url)
        try:
            result = persister.save_jobs([job])
            _merge_job_maps(jobs_by_url, result.get("jobs", {}))
            if norm_url not in jobs_by_url:
                logger.error("job_save_missing_from_response", extra={
                    "url": url,
                    "source": job.get("source"),
                })
        except Exception as exc:
            logger.error("job_save_failed", extra={
                "url": url,
                "source": job.get("source"),
                "error": str(exc),
            })

    recovered = sum(1 for url in expected_urls if url in jobs_by_url)
    if recovered < len(set(expected_urls)):
        logger.error("batch_save_fallback_incomplete", extra={
            "recovered_count": recovered,
            "expected_count": len(set(expected_urls)),
        })
    return jobs_by_url


def _persist_prescreen_f(job_data, pre_results, persister):
    """Persist a pre-screened F job (F rankings + formatted/ranked flags) — no LLM calls.

    Order is atomic-from-the-pipeline's-view: persist the F rankings FIRST (while
    the job is still is_formatted=False), and only once that POST is confirmed do
    we flip is_formatted+is_ranked together in a single patch. Both flags must be
    set in the same call because Job.save() resets is_ranked while is_formatted is
    False.

    Returns True only when rankings AND flags are persisted. Returns False if the
    rankings POST fails, leaving the job discoverable as unformatted so the caller
    can fall back to the normal format+rank chain (no silent formatted-but-unranked
    orphan).
    """
    from config import DJANGO_API_URL

    job_id = job_data["id"]
    rankings = [
        {
            "job_id": job_id,
            "profile_id": res["profile_id"],
            "profile_title": res["profile_id"],
            "match_tier": "F",
            "llm_tier": None,
            "deterministic_tier": "F",
            "match_score": 8,
            "signals": res.get("signals", {}),
            "rank": 92,
            "jd_summary": f"Pre-screened: {res.get('hard_fail_reason') or 'hard fail'}",
        }
        for res in pre_results
    ]
    try:
        resp = req.post(
            f"{DJANGO_API_URL}/api/rankings/bulk_create/",
            json=rankings,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("prescreen_f_rankings_failed", extra={"job_id": job_id, "error": str(exc)})
        return False

    # Rankings are saved — now mark formatted+ranked atomically so the poller
    # treats this job as fully processed.
    try:
        persister.update_job(job_id, {"is_formatted": True, "is_ranked": True})
    except Exception as exc:
        logger.warning("prescreen_f_flag_update_failed", extra={"job_id": job_id, "error": str(exc)})
        return False
    return True


def _dispatch_or_prescreen(job_data, ranker_profiles, r, pipeline_run_id, persister, job_priority):
    """Pre-screen a job and either persist F inline or dispatch the format+rank chain.

    The Redis lock for job_data['id'] must already be held by the caller.
    Returns True if dispatched to chain, False if pre-screened out (lock released,
    F rankings persisted, job marked formatted — no in-flight entry created).
    """
    import matching as _matching
    from tasks.formatting import format_and_persist_job
    from tasks.ranking import rank_job_multi_profile

    pre_fail = False
    pre_results = []
    try:
        pre_fail, pre_results = _matching.prescreen_hard_fail(
            job_data.get("raw_data") or {}, ranker_profiles
        )
    except Exception as exc:
        logger.warning("prescreen_error", extra={"job_id": job_data.get("id"), "error": str(exc)})

    if pre_fail:
        logger.info("job_prescreened_f", extra={
            "job_id": job_data.get("id"),
            "reasons": [res.get("hard_fail_reason") for res in pre_results],
        })
        if _persist_prescreen_f(job_data, pre_results, persister):
            r.delete(f"job_processing_lock:{job_data['id']}")
            return False
        # Persist failed (transient API error) — fall through to normal chain so the
        # job is not silently dropped; it will be re-screened on the next scrape.
        logger.warning("prescreen_f_persist_failed_falling_back", extra={"job_id": job_data.get("id")})

    job_id = job_data["id"]
    r.sadd(f"pipeline:{pipeline_run_id}:in_flight", job_id)
    r.hset(f"pipeline:{pipeline_run_id}:dispatched_at", job_id, time.time())
    r.incr(f"pipeline:{pipeline_run_id}:total_jobs")
    chain(
        format_and_persist_job.s(job_data).set(priority=job_priority),
        rank_job_multi_profile.s(
            profiles=ranker_profiles,
            pipeline_run_id=pipeline_run_id,
            job_id=job_id,
        ).set(priority=job_priority),
    ).apply_async()
    return True


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}

# Redis key holding the latest Apify quota/credit problem (shown on the dashboard).
APIFY_QUOTA_ALERT_KEY = "apify:quota_alert"
# Substrings in an Apify error that indicate the account is out of usage/credits.
_QUOTA_ERROR_HINTS = (
    "usage", "quota", "credit", "hard limit", "limit exceeded",
    "monthly", "payment required", "402", "insufficient",
)


def _looks_like_quota_error(exc):
    msg = str(exc).lower()
    return any(hint in msg for hint in _QUOTA_ERROR_HINTS)


def _flag_apify_quota_alert(r, actor_id, exc):
    import json as _json
    payload = _json.dumps({
        "message": str(exc)[:300],
        "actor_id": actor_id,
        "at": datetime.utcnow().isoformat() + "Z",
    })
    # Auto-expire after a week so a one-off blip doesn't linger forever.
    r.set(APIFY_QUOTA_ALERT_KEY, payload, ex=7 * 86400)


def _extract_job_dict(raw_job, source="custom"):
    """Build a minimal stub dict from raw scraper output (no HTTP calls)."""
    return {
        "title": (raw_job.get("title") or raw_job.get("position")
                  or raw_job.get("standardizedTitle") or "Unknown"),
        "company": (raw_job.get("company") or raw_job.get("companyName")
                    or raw_job.get("company_name") or "Unknown"),
        "url": (raw_job.get("url") or raw_job.get("jobUrl")
                or raw_job.get("link") or raw_job.get("applyUrl") or ""),
        "source": source,
        "salary": "",
        "description": "",
        "full_description": "",
        "raw_data": raw_job,
    }




def _load_profiles_for_ranking(profile_ids):
    import json as _json
    if not hasattr(_load_profiles_for_ranking, "cache"):
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        profiles_path = os.path.join(base_dir, "user-profiles.json")
        with open(profiles_path, "r", encoding="utf-8") as f:
            _load_profiles_for_ranking.cache = _json.load(f)
    profiles = _load_profiles_for_ranking.cache
    if profile_ids:
        profiles = [p for p in profiles if p.get("id") in profile_ids]
    return profiles


@app.task(bind=True, name='tasks.pipeline.poll_actor_dataset', max_retries=1000)
def poll_actor_dataset(self, run_id, dataset_id, actor_id, source, profile_ids, pipeline_run_id, offset, location=None):
    """Async polling: fetches a batch of items, dispatches format/rank, and retries if more items exist or actor is running."""
    client = ApifyClient(get_apify_api_token())
    persister = DjangoPersistence()
    ranker_profiles = _load_profiles_for_ranking(profile_ids)
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    
    # 1. Fetch
    try:
        page = client.dataset(dataset_id).list_items(offset=offset, limit=POLL_BATCH_SIZE)
    except (RequestException, ApifyApiError, TimeoutError) as exc:
        raise self.retry(exc=exc, countdown=min(2 ** self.request.retries, 60))
        
    items = page.items
    batch_size = len(items)
    
    # 2. Process — batch-save all stubs in one POST, then dispatch in-memory.
    if batch_size > 0:
        from tasks.formatting import format_and_persist_job
        from tasks.ranking import rank_job_multi_profile

        job_priority = 9 if location == "japan_tokyo" else 5

        # Build stubs for every item in the page (no HTTP calls yet).
        batch_jobs = []
        stub_by_url = {}  # normalized_url → raw job_dict (for dispatch below)
        for item in items:
            jd = _extract_job_dict(item, source=source)
            if jd.get("url"):
                norm = normalize_url(jd["url"])
                batch_jobs.append(jd)
                stub_by_url[norm] = jd

        # One HTTP POST for the whole page → returns {normalized_url: {id, is_formatted}}.
        jobs_by_url = _save_jobs_with_fallback(persister, batch_jobs)

        # Dispatch in-memory using the response map — zero follow-up GETs.
        for norm_url, job_dict in stub_by_url.items():
            try:
                db_info = jobs_by_url.get(norm_url)
                if not db_info:
                    continue

                if db_info.get("is_formatted"):
                    logger.info("job_already_processed_skipping", extra={"url": job_dict.get("url", "")})
                    continue

                job_id = db_info["id"]
                if not r.set(f"job_processing_lock:{job_id}", "1", nx=True, ex=3600):
                    logger.info("job_already_in_progress_skipping", extra={"url": job_dict.get("url", "")})
                    continue

                job_data = {
                    "id": job_id,
                    "title": job_dict.get("title", "Unknown"),
                    "company": job_dict.get("company", "Unknown"),
                    "url": job_dict.get("url", ""),
                    "source": job_dict.get("source", source),
                    "raw_data": job_dict.get("raw_data", {}),
                    "pipeline_run_id": pipeline_run_id,
                }

                _dispatch_or_prescreen(
                    job_data, ranker_profiles, r, pipeline_run_id, persister, job_priority
                )


            except Exception as exc:
                logger.error("item_dispatch_failed", extra={"error": str(exc)})

        offset += batch_size
        retry_kwargs = self.request.kwargs.copy()
        retry_kwargs["offset"] = offset
        raise self.retry(countdown=2, kwargs=retry_kwargs)

    # 3. If no new items, check actor status
    try:
        run_info = client.run(run_id).get()
        final_status = run_info.get("status", "UNKNOWN")
    except (RequestException, ApifyApiError, TimeoutError) as exc:
        raise self.retry(exc=exc, countdown=10)

    # 4. Decide whether to stop
    if final_status in TERMINAL_STATUSES:
        # Actor is finished and no new items!
        r.decr(f"pipeline:{pipeline_run_id}:active_actors")
        logger.info(f"Actor {actor_id} finished. Run {pipeline_run_id} updated.")
        
        active = int(r.get(f"pipeline:{pipeline_run_id}:active_actors") or 0)
        in_flight_count = r.scard(f"pipeline:{pipeline_run_id}:in_flight")
        
        if active <= 0 and in_flight_count <= 0:
            if r.set(f"pipeline:{pipeline_run_id}:summary_sent", "1", nx=True, ex=86400):
                send_discord_summary.delay(pipeline_run_id)
            # Cleanup redis keys safely
            r.delete(f"pipeline:{pipeline_run_id}:active_actors")
            r.delete(f"pipeline:{pipeline_run_id}:in_flight")
            r.delete(f"pipeline:{pipeline_run_id}:dispatched_at")
            
        return {"status": "done", "actor_id": actor_id}
        
    # Actor still running, no new items yet. Retry in 10s.
    retry_kwargs = self.request.kwargs.copy()
    retry_kwargs["offset"] = offset
    raise self.retry(countdown=10, kwargs=retry_kwargs)


@app.task(bind=True, name='tasks.pipeline.start_actor')
def start_actor(self, actor_id, run_input, source, profile_ids, pipeline_run_id,
                fallback_actors=None, location=None):
    """Starts the Apify actor and kicks off the async polling.

    If the primary actor fails to start (quota exhausted, actor outage, bad
    input), each entry in `fallback_actors` is tried in order before the run is
    counted as a lost actor. This keeps a single dead actor from silently
    dropping a whole source/location for the day.
    """
    client = ApifyClient(get_apify_api_token())

    # Primary first, then any configured fallbacks.
    candidates = [{"actor_id": actor_id, "input": run_input}]
    for fb in (fallback_actors or []):
        if fb and fb.get("actor_id"):
            candidates.append({"actor_id": fb["actor_id"], "input": fb.get("input", run_input)})

    last_exc = None
    for attempt in candidates:
        a_id = attempt["actor_id"]
        try:
            run = client.actor(a_id).start(run_input=attempt["input"])
            run_id = run["id"]
            dataset_id = run["defaultDatasetId"]

            poll_actor_dataset.delay(
                run_id=run_id, dataset_id=dataset_id, actor_id=a_id,
                source=source, profile_ids=profile_ids,
                pipeline_run_id=pipeline_run_id, offset=0, location=location
            )
            if a_id != actor_id:
                logger.warning("actor_fallback_used", extra={
                    "primary": actor_id, "fallback": a_id, "source": source,
                })
            print(f"   -> Started actor {a_id} (run_id: {run_id}). Async polling dispatched.")
            return
        except Exception as exc:
            last_exc = exc
            logger.error(f"Failed to start actor {a_id}: {exc}")

    # All candidates (primary + fallbacks) failed -> count this actor as lost.
    exc = last_exc
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    if exc is not None and _looks_like_quota_error(exc):
        _flag_apify_quota_alert(r, actor_id, exc)
    active = r.decr(f"pipeline:{pipeline_run_id}:active_actors")
    in_flight_count = r.scard(f"pipeline:{pipeline_run_id}:in_flight")
    if active <= 0 and in_flight_count <= 0:
        if r.set(f"pipeline:{pipeline_run_id}:summary_sent", "1", nx=True, ex=86400):
            send_discord_summary.delay(pipeline_run_id)
        r.delete(f"pipeline:{pipeline_run_id}:active_actors")
        r.delete(f"pipeline:{pipeline_run_id}:in_flight")
        r.delete(f"pipeline:{pipeline_run_id}:dispatched_at")


@app.task(name='tasks.pipeline.send_discord_summary')
def send_discord_summary(pipeline_run_id):
    """Final callback: all actors finished, all formatting/ranking jobs complete.

    Posts any S/A-ranked jobs that weren't already alerted via the per-job
    immediate notification (i.e. where alert_sent is still False).  This acts
    as a backstop for jobs whose immediate alert failed and is a no-op when
    all immediate alerts succeeded.
    """
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    total_jobs = int(r.get(f"pipeline:{pipeline_run_id}:total_jobs") or 0)
    r.delete(f"pipeline:{pipeline_run_id}:total_jobs")

    logger.info("pipeline_complete", extra={
        "pipeline_run_id": pipeline_run_id, "total_jobs": total_jobs,
    })

    try:
        from outputs import ExportHandler
        ExportHandler.post_tiered_jobs_from_api()
    except Exception as exc:
        logger.error("discord_summary_failed", extra={"error": str(exc)})

    return {"status": "done", "total_jobs": total_jobs}


@app.task(name='tasks.pipeline.run_pipeline')
def run_pipeline(actor_configs, profile_ids, run_local=True):
    """Entry point: initialize run, setup redis state, dispatch actor triggers."""
    pipeline_run_id = str(uuid.uuid4())
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    # Assume the Apify key is healthy for this run; a quota failure below re-flags it.
    r.delete(APIFY_QUOTA_ALERT_KEY)
    
    num_actors = len(actor_configs)
    if run_local:
        num_actors += 1
        
    r.set(f"pipeline:{pipeline_run_id}:active_actors", num_actors)
    r.set(f"pipeline:{pipeline_run_id}:total_jobs", 0)
    
    print(f"Booting Pipeline Run ID: {pipeline_run_id} for {len(actor_configs)} apify actors" + (" + 1 local scraper..." if run_local else "..."))
    
    # Schedule reconciliation task to run in 60 seconds
    check_pipeline_completion.apply_async(args=[pipeline_run_id], countdown=60)
    
    for config in actor_configs:
        start_actor.delay(
            config["actor_id"], config["input"],
            source=config.get("source", "custom"),
            profile_ids=profile_ids,
            pipeline_run_id=pipeline_run_id,
            fallback_actors=config.get("fallback_actors"),
            location=config.get("location"),
        )
        
    # Trigger local scrapers
    if run_local:
        run_local_scrapers.delay(profile_ids, pipeline_run_id)

@app.task(bind=True, name='tasks.pipeline.run_local_scrapers')
def run_local_scrapers(self, profile_ids, pipeline_run_id):
    """Runs local python scrapers synchronously within Celery task."""
    logger.info("Starting local scrapers for all supported job boards...")
    from locations import get_location
    japan_cfg = get_location("japan_tokyo") or {}
    limit = japan_cfg.get("local_scrape_limit", japan_cfg.get("linkedin_scrape_limit", 100))
    
    all_jobs = []
    
    try:
        all_jobs.extend(scrape_japan_dev(limit=limit))
    except Exception as e:
        logger.error(f"Japan-Dev scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_tokyo_dev(limit=limit))
    except Exception as e:
        logger.error(f"Tokyo-Dev scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_gaijinpot(limit=limit))
    except Exception as e:
        logger.error(f"GaijinPot scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_careercross(limit=limit))
    except Exception as e:
        logger.error(f"CareerCross scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_green(limit=limit))
    except Exception as e:
        logger.error(f"Green scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_daijob(limit=limit))
    except Exception as e:
        logger.error(f"Daijob scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_wantedly(limit=limit))
    except Exception as e:
        logger.error(f"Wantedly scraper failed: {e}")
        
    persister = DjangoPersistence()
    ranker_profiles = _load_profiles_for_ranking(profile_ids)
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    
    from tasks.formatting import format_and_persist_job
    from tasks.ranking import rank_job_multi_profile

    # Batch-save all stubs in one POST, then dispatch in-memory.
    batch_jobs = []
    stub_by_url = {}
    for item in all_jobs:
        src = item.get("source", "custom")
        jd = _extract_job_dict(item, source=src)
        if jd.get("url"):
            norm = normalize_url(jd["url"])
            batch_jobs.append(jd)
            stub_by_url[norm] = jd

    jobs_by_url = _save_jobs_with_fallback(persister, batch_jobs)

    for norm_url, job_dict in stub_by_url.items():
        try:
            db_info = jobs_by_url.get(norm_url)
            if not db_info:
                continue

            if db_info.get("is_formatted"):
                continue

            job_id = db_info["id"]
            if not r.set(f"job_processing_lock:{job_id}", "1", nx=True, ex=3600):
                continue

            job_data = {
                "id": job_id,
                "title": job_dict.get("title", "Unknown"),
                "company": job_dict.get("company", "Unknown"),
                "url": job_dict.get("url", ""),
                "source": job_dict.get("source", "custom"),
                "raw_data": job_dict.get("raw_data", {}),
                "pipeline_run_id": pipeline_run_id,
            }

            _dispatch_or_prescreen(
                job_data, ranker_profiles, r, pipeline_run_id, persister, job_priority=9
            )


        except Exception as exc:
            logger.error("item_dispatch_failed", extra={"error": str(exc)})
            
    # Mark local scrapers as finished
    active = r.decr(f"pipeline:{pipeline_run_id}:active_actors")
    logger.info(f"Local scrapers finished. Active actors remaining: {active}")
    
    in_flight_count = r.scard(f"pipeline:{pipeline_run_id}:in_flight")
    if active <= 0 and in_flight_count <= 0:
        if r.set(f"pipeline:{pipeline_run_id}:summary_sent", "1", nx=True, ex=86400):
            send_discord_summary.delay(pipeline_run_id)
        r.delete(f"pipeline:{pipeline_run_id}:active_actors")
        r.delete(f"pipeline:{pipeline_run_id}:in_flight")
        r.delete(f"pipeline:{pipeline_run_id}:dispatched_at")

@app.task(name='tasks.pipeline.run_pipeline_from_config')
def run_pipeline_from_config():
    """Reads actor-config.json and triggers the pipeline for all defined actors."""
    import json
    import os
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "actor-config.json")
    if not os.path.exists(config_path):
        logger.warning(f"Actor config {config_path} not found.")
        return
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            actor_configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {config_path}: {e}")
        return
        
    profiles = _load_profiles_for_ranking(None)
    profile_ids = [p["id"] for p in profiles]
    
    if actor_configs:
        logger.info(f"Triggering pipeline for all {len(actor_configs)} scrapers.")
        run_pipeline.delay(actor_configs, profile_ids)
    else:
        logger.info("No scrapers configured in actor-config.json.")


@app.task(name='tasks.pipeline.run_linkedin_pipeline')
def run_linkedin_pipeline():
    """Reads actor-config.json, filters for LinkedIn scrapers, and triggers the pipeline (excludes local scrapers)."""
    import json
    import os
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "actor-config.json")
    if not os.path.exists(config_path):
        logger.warning(f"Actor config {config_path} not found.")
        return
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            actor_configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {config_path}: {e}")
        return
        
    linkedin_configs = [c for c in actor_configs if c.get("source") == "linkedin"]
    profiles = _load_profiles_for_ranking(None)
    profile_ids = [p["id"] for p in profiles]
    
    if linkedin_configs:
        logger.info(f"Triggering LinkedIn-only pipeline for all {len(linkedin_configs)} scrapers.")
        run_pipeline.delay(linkedin_configs, profile_ids, run_local=False)
    else:
        logger.info("No LinkedIn scrapers configured in actor-config.json.")


@app.task(name='tasks.pipeline.run_indeed_pipeline')
def run_indeed_pipeline():
    """Reads actor-config.json, filters for Indeed scrapers, and triggers the pipeline (excludes local scrapers)."""
    import json
    import os
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "actor-config.json")
    if not os.path.exists(config_path):
        logger.warning(f"Actor config {config_path} not found.")
        return
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            actor_configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {config_path}: {e}")
        return
        
    indeed_configs = [c for c in actor_configs if c.get("source") == "indeed"]
    profiles = _load_profiles_for_ranking(None)
    profile_ids = [p["id"] for p in profiles]
    
    if indeed_configs:
        logger.info(f"Triggering Indeed-only pipeline for all {len(indeed_configs)} scrapers.")
        run_pipeline.delay(indeed_configs, profile_ids, run_local=False)
    else:
        logger.info("No Indeed scrapers configured in actor-config.json.")


@app.task(name='tasks.pipeline.run_local_pipeline')
def run_local_pipeline():
    """Triggers only local scrapers (no Apify actors)."""
    profiles = _load_profiles_for_ranking(None)
    profile_ids = [p["id"] for p in profiles]
    
    logger.info("Triggering local scrapers-only pipeline.")
    run_pipeline.delay([], profile_ids, run_local=True)


@app.task(bind=True, name='tasks.pipeline.check_pipeline_completion', max_retries=1000)
def check_pipeline_completion(self, pipeline_run_id):
    """Reconciliation task that runs periodically to check if the pipeline is finished or needs timeout cleanup."""
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    
    active_key = f"pipeline:{pipeline_run_id}:active_actors"
    in_flight_key = f"pipeline:{pipeline_run_id}:in_flight"
    dispatched_key = f"pipeline:{pipeline_run_id}:dispatched_at"
    summary_sent_key = f"pipeline:{pipeline_run_id}:summary_sent"
    
    # If summary is already sent, we are done
    if r.get(summary_sent_key):
        return {"status": "already_completed"}
        
    active = int(r.get(active_key) or 0)
    
    # If scrapers are still running, check again later
    if active > 0:
        raise self.retry(countdown=60)
        
    # Scrapers are done. Now check for timed out jobs in-flight.
    now = time.time()
    TIMEOUT_SECONDS = 300  # 5 minutes
    
    in_flight_jobs = r.smembers(in_flight_key)
    if in_flight_jobs:
        for job_id_bytes in in_flight_jobs:
            job_id = job_id_bytes.decode('utf-8')
            dispatched_at_bytes = r.hget(dispatched_key, job_id)
            if dispatched_at_bytes:
                dispatched_at = float(dispatched_at_bytes.decode('utf-8'))
                if now - dispatched_at > TIMEOUT_SECONDS:
                    logger.warning(f"Job {job_id} in pipeline {pipeline_run_id} timed out. Removing from in-flight.")
                    r.srem(in_flight_key, job_id)
                    r.hdel(dispatched_key, job_id)
                    
    # Re-evaluate in-flight count after removing timed out jobs
    in_flight_count = r.scard(in_flight_key)
    if in_flight_count <= 0:
        if r.set(summary_sent_key, "1", nx=True, ex=86400):
            send_discord_summary.delay(pipeline_run_id)
        r.delete(active_key)
        r.delete(in_flight_key)
        r.delete(dispatched_key)
        return {"status": "completed_by_reconciler"}
    
    # Still has non-timed out jobs in flight, check again soon
    raise self.retry(countdown=30)


@app.task(name='tasks.pipeline.process_unprocessed_jobs_task')
def process_unprocessed_jobs_task(profile_ids=None):
    """Fetch all unformatted jobs, format + rank them. Also fetch all formatted but unranked jobs, and rank them."""
    from jobs.models import Job
    from celery import chain
    from tasks.formatting import format_and_persist_job
    from tasks.ranking import rank_job_multi_profile

    # 1. Load profiles for ranking
    ranker_profiles = _load_profiles_for_ranking(profile_ids)
    if not ranker_profiles:
        logger.error("No profiles loaded for processing unprocessed jobs.")
        return {"status": "error", "message": "No profiles found"}

    # 2. Get all unformatted jobs
    unformatted_jobs = Job.objects.filter(is_formatted=False)
    unformatted_count = unformatted_jobs.count()

    # 3. Get all unranked jobs (formatted, but not ranked)
    unranked_jobs = Job.objects.filter(is_formatted=True, is_ranked=False)
    unranked_count = unranked_jobs.count()

    logger.info(f"Starting process_unprocessed_jobs_task: {unformatted_count} unformatted, {unranked_count} unranked jobs.")

    import redis
    from config import CELERY_BROKER_URL
    r = redis.Redis.from_url(CELERY_BROKER_URL)

    def get_job_priority(job):
        if job.source in ["japan_dev", "tokyo_dev", "gaijinpot", "careercross", "green", "daijob", "wantedly"]:
            return 9
        if job.location and ("japan" in job.location.lower() or "tokyo" in job.location.lower()):
            return 9
        return 5

    # 4. Dispatch format + rank chain for unformatted jobs
    for job in unformatted_jobs:
        # Prevent concurrent duplicate queueing (lock expires in 1 hour if it fails)
        if not r.set(f"job_processing_lock:{job.id}", "1", nx=True, ex=3600):
            continue
            
        job_data = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "source": job.source,
            "raw_data": job.raw_data,
            "pipeline_run_id": None,
        }
        job_priority = get_job_priority(job)
        chain(
            format_and_persist_job.s(job_data).set(priority=job_priority),
            rank_job_multi_profile.s(profiles=ranker_profiles, pipeline_run_id=None, job_id=job.id).set(priority=job_priority),
        ).apply_async()

    # 5. Dispatch rank directly for unranked jobs
    for job in unranked_jobs:
        if not r.set(f"job_processing_lock:{job.id}", "1", nx=True, ex=3600):
            continue

        job_data = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "salary": job.salary,
            "salary_yen": job.salary_yen,
            "experience_required": job.experience_required,
            "language": job.language,
            "description": job.description,
            "full_description": job.full_description,
            "tech_stack": job.tech_stack,
            "location": job.location,
            "region": job.region,
            "is_remote": job.is_remote,
            "source": job.source,
        }
        job_priority = get_job_priority(job)
        rank_job_multi_profile.apply_async(
            kwargs={
                "formatted_job_data": job_data,
                "profiles": ranker_profiles,
                "pipeline_run_id": None,
                "job_id": job.id
            },
            priority=job_priority
        )

    return {
        "status": "success",
        "unformatted_processed": unformatted_count,
        "unranked_processed": unranked_count,
    }


@app.task(name='tasks.pipeline.deactivate_stale_jobs')
def deactivate_stale_jobs(days=30):
    """Mark jobs not seen in `days` days as inactive so they stop polluting stats.

    A job re-seen in a scrape gets its updated_at bumped (update_or_create), so
    updated_at is the effective "last seen" timestamp.
    """
    from datetime import timedelta
    from django.utils import timezone
    from jobs.models import Job

    cutoff = timezone.now() - timedelta(days=days)
    deactivated = Job.objects.filter(is_active=True, updated_at__lt=cutoff).update(is_active=False)
    logger.info(f"deactivate_stale_jobs: deactivated {deactivated} jobs not updated in {days} days.")
    return {"status": "success", "deactivated": deactivated, "cutoff_days": days}
