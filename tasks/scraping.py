import logging

from celery.exceptions import SoftTimeLimitExceeded
from celery_app import app
from apify_client import ApifyClient
from config import get_apify_api_token
from scrapers import JobScraperPipeline, poll_and_persist
from persistence import DjangoPersistence

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name='tasks.scraping.scrape_actor',
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=900,
)
def scrape_actor(self, actor_id, run_input, source=None):
    """Start an Apify actor asynchronously and persist dataset items incrementally."""
    client = ApifyClient(get_apify_api_token())
    pipeline = JobScraperPipeline()
    persister = DjangoPersistence()

    # --- Start actor (non-blocking) ---
    try:
        run = client.actor(actor_id).start(run_input=run_input)
    except Exception as exc:
        logger.error("actor_start_failed", extra={
            "actor_id": actor_id, "error": str(exc),
        })
        raise self.retry(exc=exc)

    run_id = run["id"]
    dataset_id = run["defaultDatasetId"]
    logger.info("actor_started", extra={
        "actor_id": actor_id, "run_id": run_id, "dataset_id": dataset_id,
    })

    # Clean + tag with source for DB persistence
    def clean_and_tag(items):
        cleaned = pipeline.clean_payload(items)
        if source:
            for item in cleaned:
                item["source"] = source
        return cleaned

    try:
        result = poll_and_persist(
            client, run_id, dataset_id,
            clean_fn=clean_and_tag,
            persist_fn=persister.save_jobs,
        )
    except SoftTimeLimitExceeded:
        logger.warning("soft_timeout", extra={
            "actor_id": actor_id, "run_id": run_id,
        })
        # Return partial metadata — items already persisted are safe
        return {
            "actor_id": actor_id,
            "run_id": run_id,
            "total_jobs": 0,
            "status": "SOFT_TIMEOUT",
        }

    return {
        "actor_id": actor_id,
        "run_id": run_id,
        "total_jobs": result["total_processed"],
        "status": result["final_status"],
    }
