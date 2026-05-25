import json
import logging
import time

from apify_client import ApifyClient
from apify_client._errors import ApifyApiError
from requests.exceptions import RequestException
from config import APIFY_API_TOKEN

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3
POLL_BATCH_SIZE = 1000
ACTOR_POLL_TIMEOUT_SECS = 3600  # max time waiting for actor to reach terminal status (40 min for slow actors like tokyo-dev)
IDLE_TIMEOUT_SECS = 300        # stop early if actor is done and no new items

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def poll_and_persist(client, run_id, dataset_id, clean_fn, persist_fn,
                     actor_timeout=ACTOR_POLL_TIMEOUT_SECS,
                     idle_timeout=IDLE_TIMEOUT_SECS):
    """Poll an Apify dataset incrementally, cleaning and persisting each batch.

    Polling loop order:
      1. Fetch dataset items at current offset
      2. Clean and persist the batch
      3. Check actor run status
      4. Decide whether to stop (terminal status + no new items, or idle timeout)

    This ordering ensures we never miss final dataset flushes by checking
    completion before consuming the latest items.
    """
    offset = 0
    last_item_time = time.time()
    total_processed = 0
    polls = 0
    retries = 0
    start_time = time.time()
    final_status = "UNKNOWN"

    while True:
        elapsed = time.time() - start_time

        # --- Step 1: Fetch dataset items ---
        try:
            page = client.dataset(dataset_id).list_items(
                offset=offset, limit=POLL_BATCH_SIZE,
            )
            retries = 0
        except (RequestException, ApifyApiError, TimeoutError) as exc:
            retries += 1
            backoff = min(2 ** retries, 30)
            logger.warning("poll_error", extra={
                "actor_id": run_id, "error": str(exc),
                "retry_count": retries, "offset": offset,
            })
            time.sleep(backoff)
            continue

        items = page.items
        batch_size = len(items)

        # --- Step 2: Clean and persist batch ---
        if batch_size > 0:
            try:
                cleaned = clean_fn(items)
                if cleaned:
                    persist_fn(cleaned)
            except Exception as exc:
                logger.error("batch_persist_failed", extra={
                    "run_id": run_id, "batch_size": batch_size,
                    "error": str(exc),
                })

            offset += batch_size
            total_processed += batch_size
            last_item_time = time.time()
            logger.info("batch_persisted", extra={
                "run_id": run_id, "batch_size": batch_size,
                "total_processed": total_processed, "offset": offset,
            })

        # --- Step 3: Check actor status ---
        try:
            run_info = client.run(run_id).get()
            if run_info:
                final_status = run_info.get("status", "UNKNOWN")
        except (RequestException, ApifyApiError, TimeoutError):
            pass

        # --- Step 4: Decide whether to stop ---
        # Stop only when actor reached terminal status AND no new items remain
        if final_status in TERMINAL_STATUSES and batch_size == 0:
            break

        # If actor is still running but no new items, keep polling
        # (don't give up on a slow actor that hasn't finished yet)
        if final_status not in TERMINAL_STATUSES:
            if elapsed > actor_timeout:
                logger.warning("actor_timeout", extra={
                    "run_id": run_id, "actor_status": final_status,
                    "elapsed_secs": round(elapsed),
                    "total_processed": total_processed,
                })
                break
        else:
            # Actor finished but still had stale items; use idle timeout
            if batch_size == 0:
                idle_secs = time.time() - last_item_time
                if idle_secs > idle_timeout:
                    logger.warning("idle_timeout", extra={
                        "run_id": run_id, "idle_secs": round(idle_secs),
                        "total_processed": total_processed,
                    })
                    break

        # --- Step 5: Wait before next poll ---
        time.sleep(POLL_INTERVAL)
        polls += 1

    elapsed = round(time.time() - start_time, 1)
    logger.info("actor_finished", extra={
        "run_id": run_id, "status": final_status,
        "total_items": total_processed, "polls": polls,
        "elapsed_secs": elapsed,
    })

    return {
        "total_processed": total_processed,
        "final_status": final_status,
        "polls": polls,
    }


def poll_items(client, run_id, dataset_id,
               actor_timeout=ACTOR_POLL_TIMEOUT_SECS,
               idle_timeout=IDLE_TIMEOUT_SECS):
    """Generator that yields individual items from an Apify dataset as they become available.

    Same polling logic as poll_and_persist but yields items one at a time
    for immediate per-item processing (format → rank).
    Returns a summary dict after the actor completes.
    """
    offset = 0
    last_item_time = time.time()
    total_processed = 0
    polls = 0
    retries = 0
    start_time = time.time()
    final_status = "UNKNOWN"

    while True:
        elapsed = time.time() - start_time

        # --- Step 1: Fetch dataset items ---
        try:
            page = client.dataset(dataset_id).list_items(
                offset=offset, limit=POLL_BATCH_SIZE,
            )
            retries = 0
        except (RequestException, ApifyApiError, TimeoutError) as exc:
            retries += 1
            backoff = min(2 ** retries, 30)
            logger.warning("poll_error", extra={
                "actor_id": run_id, "error": str(exc),
                "retry_count": retries, "offset": offset,
            })
            time.sleep(backoff)
            continue

        items = page.items
        batch_size = len(items)

        # --- Step 2: Yield each item individually ---
        if batch_size > 0:
            for item in items:
                yield item
                total_processed += 1

            offset += batch_size
            last_item_time = time.time()
            logger.info("batch_yielded", extra={
                "run_id": run_id, "batch_size": batch_size,
                "total_processed": total_processed, "offset": offset,
            })

        # --- Step 3: Check actor status ---
        try:
            run_info = client.run(run_id).get()
            if run_info:
                final_status = run_info.get("status", "UNKNOWN")
        except (RequestException, ApifyApiError, TimeoutError):
            pass

        # --- Step 4: Decide whether to stop ---
        if final_status in TERMINAL_STATUSES and batch_size == 0:
            break

        if final_status not in TERMINAL_STATUSES:
            if elapsed > actor_timeout:
                logger.warning("actor_timeout", extra={
                    "run_id": run_id, "actor_status": final_status,
                    "elapsed_secs": round(elapsed),
                    "total_processed": total_processed,
                })
                break
        else:
            if batch_size == 0:
                idle_secs = time.time() - last_item_time
                if idle_secs > idle_timeout:
                    logger.warning("idle_timeout", extra={
                        "run_id": run_id, "idle_secs": round(idle_secs),
                        "total_processed": total_processed,
                    })
                    break

        # --- Step 5: Wait before next poll ---
        time.sleep(POLL_INTERVAL)
        polls += 1

    elapsed = round(time.time() - start_time, 1)
    logger.info("actor_finished", extra={
        "run_id": run_id, "status": final_status,
        "total_items": total_processed, "polls": polls,
        "elapsed_secs": elapsed,
    })

    # Signal end of iteration with a summary
    yield {"_done": True, "total_processed": total_processed,
           "final_status": final_status, "polls": polls, "elapsed_secs": elapsed}


class JobScraperPipeline:
    def __init__(self):
        self.client = ApifyClient(APIFY_API_TOKEN)

    def load_json_file(self, filepath):
        with open(filepath, 'r') as f:
            return json.load(f)

    def run_all_actors(self, config_path="actor-config.json"):
        """Iterates through actor-config.json, starts each actor asynchronously,
        and persists dataset items incrementally via polling."""
        from persistence import DjangoPersistence
        actor_configs = self.load_json_file(config_path)
        persister = DjangoPersistence()

        print("\n🕸️  Phase 1: Scraping Data via Apify")
        for config in actor_configs:
            actor_id = config["actor_id"]
            run_input = config["input"]
            print(f"   -> Starting actor {actor_id}...")

            try:
                run = self.client.actor(actor_id).start(run_input=run_input)
                result = poll_and_persist(
                    self.client, run["id"], run["defaultDatasetId"],
                    clean_fn=self.clean_payload,
                    persist_fn=persister.save_jobs,
                )
                print(f"   ✅ Actor {actor_id}: {result['total_processed']} jobs "
                      f"({result['final_status']})")
            except Exception as e:
                print(f"   ❌ Error executing actor {actor_id}: {e}")

    def clean_payload(self, raw_jobs):
        """Minimal normalization for dedup + display, preserves full raw_data."""
        cleaned_jobs = []
        for job in raw_jobs:
            title = (
                job.get("title")
                or job.get("position")
                or job.get("standardizedTitle")
                or "Unknown"
            )
            company = (
                job.get("company")
                or job.get("companyName")
                or job.get("company_name")
                or "Unknown"
            )
            url = (
                job.get("url")
                or job.get("jobUrl")
                or job.get("link")
                or job.get("applyUrl")
                or ""
            )

            # Pass through a minimal record with the full raw object
            cleaned_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "salary": "",
                "description": "",
                "full_description": "",
                "raw_data": job,
            })
        print(f"🧹 Phase 2: Preserved {len(cleaned_jobs)} raw job objects.")
        return cleaned_jobs
