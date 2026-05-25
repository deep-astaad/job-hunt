import logging
from datetime import datetime
from celery import group, chord, chain
from celery_app import app
from persistence import DjangoPersistence
from scrapers import poll_items

logger = logging.getLogger(__name__)


def clean_and_save_item(raw_job, persister, source="custom"):
    """Clean a single raw Apify item and persist to DB. Returns (job_dict, db_records)."""
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


@app.task(
    bind=True,
    name='tasks.pipeline.scrape_actor',
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=3000,
)
def scrape_actor_stream(self, actor_id, run_input, source="custom", profile_ids=None):
    """Scrape one Apify actor. For each job: save to DB, dispatch format -> rank chain.

    Returns a summary dict when done.
    """
    from apify_client import ApifyClient
    from config import APIFY_API_TOKEN
    from tasks.formatting import format_and_persist_job
    from tasks.ranking import rank_job_multi_profile

    if profile_ids is None:
        profile_ids = []

    client = ApifyClient(APIFY_API_TOKEN)
    persister = DjangoPersistence()

    # Load profiles for the ranking task
    ranker_profiles = _load_profiles_for_ranking(profile_ids)

    total_saved = 0
    errors = 0

    print(f"   -> Starting actor {actor_id} (streaming per-item)...")

    try:
        run = client.actor(actor_id).start(run_input=run_input)
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]

        for item in poll_items(client, run_id, dataset_id):
            if isinstance(item, dict) and item.get("_done"):
                continue

            try:
                # Step 1: Save raw job to DB
                job_dict, save_result = clean_and_save_item(item, persister, source=source)
                total_saved += 1

                # Step 2: Fetch the job_id needed for downstream tasks
                job_id = persister._fetch_job_id_by_url(job_dict.get("url", ""))
                if not job_id:
                    errors += 1
                    logger.warning("no_job_id_after_save", extra={
                        "url": job_dict.get("url", ""),
                    })
                    continue

                # Step 3: Dispatch format -> rank chain
                job_data = {
                    "id": job_id,
                    "title": job_dict.get("title", "Unknown"),
                    "company": job_dict.get("company", "Unknown"),
                    "url": job_dict.get("url", ""),
                    "source": job_dict.get("source", source),
                    "raw_data": job_dict.get("raw_data", {}),
                }

                chain(
                    format_and_persist_job.s(job_data),
                    rank_job_multi_profile.s(profiles=ranker_profiles),
                ).apply_async()

            except Exception as exc:
                errors += 1
                logger.error("item_dispatch_failed", extra={
                    "actor_id": actor_id, "error": str(exc),
                })

        print(f"   ✅ Actor {actor_id}: {total_saved} saved, "
              f"{errors} errors")

    except Exception as exc:
        print(f"   ❌ Error executing actor {actor_id}: {exc}")
        return {
            "actor_id": actor_id, "source": source,
            "total_saved": total_saved, "errors": errors,
            "status": "error",
        }

    return {
        "actor_id": actor_id, "source": source,
        "total_saved": total_saved, "errors": errors,
        "status": "done",
    }


def _load_profiles_for_ranking(profile_ids):
    """Load profiles from user-profiles.json, filtered to requested IDs."""
    import json as _json
    with open("user-profiles.json", "r", encoding="utf-8") as f:
        profiles = _json.load(f)
    if profile_ids:
        profiles = [p for p in profiles if p.get("id") in profile_ids]
    return profiles


@app.task(name='tasks.pipeline.send_discord_summary')
def send_discord_summary(scrape_results):
    """Chord callback: all scrapers done. Send Discord summary."""
    from config import DISCORD_WEBHOOK_URL
    import requests as req

    total_saved = sum(r.get("total_saved", 0) for r in scrape_results if r)
    sources = {}
    for r in scrape_results:
        if r:
            src = r.get("source", "unknown")
            sources[src] = sources.get(src, 0) + r.get("total_saved", 0)

    print(f"\n📊 Pipeline complete: {total_saved} jobs scraped")
    for src, count in sources.items():
        print(f"   {src}: {count} jobs")

    if DISCORD_WEBHOOK_URL:
        try:
            source_lines = "\n".join(f"  - {src}: {count}" for src, count in sources.items())
            content = (
                f"✅ **Pipeline Complete**\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"{'-'*40}\n"
                f"Jobs scraped: **{total_saved}**\n\n"
                f"**By source:**\n{source_lines}\n\n"
                f"_Formatting and ranking dispatched as async tasks._"
            )
            req.post(DISCORD_WEBHOOK_URL, json={"content": content})
            print("   -> Discord summary sent.")
        except Exception as e:
            print(f"   -> Discord send failed: {e}")
    else:
        print("   -> Discord webhook not configured, skipping.")

    # Also send S/A ranked jobs via the existing method
    try:
        from outputs import ExportHandler
        ExportHandler.post_tiered_jobs_from_api()
    except Exception as e:
        print(f"   -> S/A Discord post failed: {e}")

    # Trigger Phase 2: batch ranking for proper job ordering within tiers
    try:
        from tasks.ranking import rank_jobs_by_profile
        rank_jobs_by_profile.apply_async(countdown=120)
        print("   -> Phase 2 batch ranking dispatched (120s delay).")
    except Exception as e:
        print(f"   -> Phase 2 dispatch failed: {e}")

    return {"status": "done", "total_saved": total_saved}


@app.task(name='tasks.pipeline.run_pipeline')
def run_pipeline(actor_configs, profile_ids):
    """Entry point: dispatch parallel scraping tasks.

    Each scrape_actor_stream task saves jobs and dispatches format -> rank chains.
    When all scrapers finish, send_discord_summary fires.
    """
    scrape_group = group(
        scrape_actor_stream.s(
            config["actor_id"], config["input"],
            source=config.get("source", "custom"),
            profile_ids=profile_ids,
        )
        for config in actor_configs
    )
    chord(scrape_group)(send_discord_summary.s())
