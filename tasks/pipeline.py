import logging
import time
import uuid
from datetime import datetime
from celery import chain
from celery_app import app
from persistence import DjangoPersistence
from config import get_apify_api_token, CELERY_BROKER_URL, DISCORD_WEBHOOK_URL
import redis
import requests as req
from apify_client import ApifyClient
from apify_client._errors import ApifyApiError
from requests.exceptions import RequestException

from local_scrapers import scrape_japan_dev, scrape_tokyo_dev

logger = logging.getLogger(__name__)

POLL_BATCH_SIZE = 1000
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


def clean_and_save_item(raw_job, persister, source="custom"):
    title = (
        raw_job.get("title")
        or raw_job.get("position")
        or raw_job.get("standardizedTitle")
        or "Unknown"
    )
    company = (
        raw_job.get("company")
        or raw_job.get("companyName")
        or raw_job.get("company_name")
        or "Unknown"
    )
    url = (
        raw_job.get("url")
        or raw_job.get("jobUrl")
        or raw_job.get("link")
        or raw_job.get("applyUrl")
        or ""
    )

    job_dict = {
        "title": title,
        "company": company,
        "url": url,
        "source": source,
        "salary": "",
        "description": "",
        "full_description": "",
        "raw_data": raw_job,
    }

    try:
        result = persister.save_jobs([job_dict])
        return job_dict, result
    except Exception as exc:
        logger.warning("save_failed", extra={"url": url, "error": str(exc)})
        return job_dict, None


def _load_profiles_for_ranking(profile_ids):
    import json as _json
    if not getattr(_load_profiles_for_ranking, "cache", None):
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
def poll_actor_dataset(self, run_id, dataset_id, actor_id, source, profile_ids, pipeline_run_id, offset):
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
    
    # 2. Process
    if batch_size > 0:
        for item in items:
            try:
                job_dict, save_result = clean_and_save_item(item, persister, source=source)
                db_job = persister._fetch_job_by_url(job_dict.get("url", ""))
                if not db_job:
                    continue
                
                # Skip if already formatted and processed
                if db_job.get("is_formatted"):
                    logger.info("job_already_processed_skipping", extra={"url": job_dict.get("url", "")})
                    continue
                
                # Prevent concurrent duplicate queueing (lock expires in 1 hour if it fails)
                if not r.set(f"job_processing_lock:{db_job['id']}", "1", nx=True, ex=3600):
                    logger.info("job_already_in_progress_skipping", extra={"url": job_dict.get("url", "")})
                    continue
                
                job_data = {
                    "id": db_job["id"],
                    "title": job_dict.get("title", "Unknown"),
                    "company": job_dict.get("company", "Unknown"),
                    "url": job_dict.get("url", ""),
                    "source": job_dict.get("source", source),
                    "raw_data": job_dict.get("raw_data", {}),
                }
                
                # Register in-flight job and update total count in Redis
                r.sadd(f"pipeline:{pipeline_run_id}:in_flight", db_job["id"])
                r.hset(f"pipeline:{pipeline_run_id}:dispatched_at", db_job["id"], time.time())
                r.incr(f"pipeline:{pipeline_run_id}:total_jobs")
                
                from tasks.formatting import format_and_persist_job
                from tasks.ranking import rank_job_multi_profile
                
                chain(
                    format_and_persist_job.s(job_data),
                    rank_job_multi_profile.s(profiles=ranker_profiles, pipeline_run_id=pipeline_run_id, job_id=db_job["id"]),
                ).apply_async()
                
            except Exception as exc:
                logger.error("item_dispatch_failed", extra={"error": str(exc)})
        
        offset += batch_size
        # Since we processed items, fetch again quickly
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
def start_actor(self, actor_id, run_input, source, profile_ids, pipeline_run_id):
    """Starts the Apify actor and kicks off the async polling."""
    client = ApifyClient(get_apify_api_token())
    try:
        run = client.actor(actor_id).start(run_input=run_input)
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]
        
        poll_actor_dataset.delay(
            run_id=run_id, dataset_id=dataset_id, actor_id=actor_id,
            source=source, profile_ids=profile_ids, 
            pipeline_run_id=pipeline_run_id, offset=0
        )
        print(f"   -> Started actor {actor_id} (run_id: {run_id}). Async polling dispatched.")
    except Exception as exc:
        logger.error(f"Failed to start actor {actor_id}: {exc}")
        r = redis.Redis.from_url(CELERY_BROKER_URL)
        if _looks_like_quota_error(exc):
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
    """Final callback: all actors finished, all formatting/ranking jobs complete."""
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    total_jobs = int(r.get(f"pipeline:{pipeline_run_id}:total_jobs") or 0)
    
    print(f"\n📊 Pipeline {pipeline_run_id} complete! {total_jobs} jobs formatted and ranked.")
        
    r.delete(f"pipeline:{pipeline_run_id}:total_jobs")
    return {"status": "done", "total_jobs": total_jobs}


@app.task(name='tasks.pipeline.run_pipeline')
def run_pipeline(actor_configs, profile_ids):
    """Entry point: initialize run, setup redis state, dispatch actor triggers."""
    pipeline_run_id = str(uuid.uuid4())
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    # Assume the Apify key is healthy for this run; a quota failure below re-flags it.
    r.delete(APIFY_QUOTA_ALERT_KEY)
    # +1 active actor for the local scrapers task
    r.set(f"pipeline:{pipeline_run_id}:active_actors", len(actor_configs) + 1)
    r.set(f"pipeline:{pipeline_run_id}:total_jobs", 0)
    
    print(f"Booting Pipeline Run ID: {pipeline_run_id} for {len(actor_configs)} apify actors + 1 local scraper...")
    
    # Schedule reconciliation task to run in 60 seconds
    check_pipeline_completion.apply_async(args=[pipeline_run_id], countdown=60)
    
    for config in actor_configs:
        start_actor.delay(
            config["actor_id"], config["input"],
            source=config.get("source", "custom"),
            profile_ids=profile_ids,
            pipeline_run_id=pipeline_run_id
        )
        
    # Trigger local scrapers
    run_local_scrapers.delay(profile_ids, pipeline_run_id)

@app.task(bind=True, name='tasks.pipeline.run_local_scrapers')
def run_local_scrapers(self, profile_ids, pipeline_run_id):
    """Runs local python scrapers (Japan-Dev, Tokyo-Dev) synchronously within Celery task."""
    logger.info("Starting local scrapers for Japan-Dev and Tokyo-Dev...")
    all_jobs = []
    
    try:
        all_jobs.extend(scrape_japan_dev(limit=50))
    except Exception as e:
        logger.error(f"Japan-Dev scraper failed: {e}")
        
    try:
        all_jobs.extend(scrape_tokyo_dev(limit=50))
    except Exception as e:
        logger.error(f"Tokyo-Dev scraper failed: {e}")
        
    persister = DjangoPersistence()
    ranker_profiles = _load_profiles_for_ranking(profile_ids)
    r = redis.Redis.from_url(CELERY_BROKER_URL)
    
    for item in all_jobs:
        try:
            source = item.get("source", "custom")
            job_dict, save_result = clean_and_save_item(item, persister, source=source)
            db_job = persister._fetch_job_by_url(job_dict.get("url", ""))
            if not db_job:
                continue
                
            if db_job.get("is_formatted"):
                continue
                
            if not r.set(f"job_processing_lock:{db_job['id']}", "1", nx=True, ex=3600):
                continue
                
            job_data = {
                "id": db_job["id"],
                "title": job_dict.get("title", "Unknown"),
                "company": job_dict.get("company", "Unknown"),
                "url": job_dict.get("url", ""),
                "source": job_dict.get("source", source),
                "raw_data": job_dict.get("raw_data", {}),
            }
            
            r.sadd(f"pipeline:{pipeline_run_id}:in_flight", db_job["id"])
            r.hset(f"pipeline:{pipeline_run_id}:dispatched_at", db_job["id"], time.time())
            r.incr(f"pipeline:{pipeline_run_id}:total_jobs")
            
            from tasks.formatting import format_and_persist_job
            from tasks.ranking import rank_job_multi_profile
            
            chain(
                format_and_persist_job.s(job_data),
                rank_job_multi_profile.s(profiles=ranker_profiles, pipeline_run_id=pipeline_run_id, job_id=db_job["id"]),
            ).apply_async()
            
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

@app.task(name='tasks.pipeline.schedule_daily_scrapers')
def schedule_daily_scrapers():
    """Reads actor-config.json and triggers actors based on their schedule_frequency."""
    import json
    import os
    from datetime import date
    
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
    
    today = date.today()
    day_of_year = today.timetuple().tm_yday
    weekday = today.weekday() # Monday is 0, Sunday is 6
    
    to_run = []
    for config in actor_configs:
        freq = config.get("schedule_frequency", "daily")
        
        if freq == "daily":
            to_run.append(config)
        elif freq == "every_2_days":
            if day_of_year % 2 == 0:
                to_run.append(config)
        elif freq == "weekly":
            if weekday == 0: # Monday
                to_run.append(config)
                
    if to_run:
        logger.info(f"Scheduled {len(to_run)} scrapers for today.")
        run_pipeline.delay(to_run, profile_ids)
    else:
        logger.info("No scrapers scheduled to run today.")


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
        }
        chain(
            format_and_persist_job.s(job_data),
            rank_job_multi_profile.s(profiles=ranker_profiles, pipeline_run_id=None, job_id=job.id),
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
            "experience_required": job.experience_required,
            "language": job.language,
            "description": job.description,
            "source": job.source,
        }
        rank_job_multi_profile.delay(
            formatted_job_data=job_data,
            profiles=ranker_profiles,
            pipeline_run_id=None,
            job_id=job.id
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


