import logging
import os
from datetime import datetime
from celery import group, chord
from celery_app import app
from persistence import DjangoPersistence
from ranker import JobRankerAI
from outputs import ExportHandler
from scrapers import poll_items

logger = logging.getLogger(__name__)

# Cache for profile data to avoid repeated disk reads during per-item ranking
_profile_cache = {}


def _get_profiles():
    """Load and cache user profiles."""
    if not _profile_cache.get("data"):
        ranker = JobRankerAI()
        profiles = ranker._load_json("user-profiles.json")
        _profile_cache["data"] = profiles
    return _profile_cache["data"]


def _get_system_prompt():
    """Load and cache ranking system prompt."""
    if not _profile_cache.get("system_prompt"):
        ranker = JobRankerAI()
        _profile_cache["system_prompt"] = ranker._read_file("prompts/ranker.txt")
    return _profile_cache["system_prompt"]


def rank_single_job(job_data, profile, system_prompt):
    """Rank a single job against one profile via GPT. Returns (tier, summary) or None."""
    ranker = JobRankerAI()

    # Build a minimal table with one job for GPT
    header = "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |"
    separator = "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"

    title_company = f"{job_data.get('title', '?')} @ {job_data.get('company', '?')}"
    salary = job_data.get("salary", "") or ""
    exp = job_data.get("experience_required", "") or ""
    lang = job_data.get("language", "") or ""
    summary = (job_data.get("description", "") or "")[:200]
    url = job_data.get("url", "")

    row = f"| 1 | ? | {title_company} | {salary} | {exp} | {lang} | {summary} | [{title_company[:30]}]({url}) |"
    single_job_table = f"{header}\n{separator}\n{row}"

    user_content = (
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"Rank this single job and return the table with the Match Tier filled in.\n\n"
        f"{single_job_table}"
    )

    try:
        response = ranker.client.chat.completions.create(
            model="gpt-4o-mini",
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
            summary = rows[0][6] if len(rows[0]) > 6 else ""
            return tier.upper(), summary
    except Exception as exc:
        logger.warning("rank_single_failed", extra={
            "job_url": job_data.get("url", ""), "error": str(exc),
        })

    return None


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
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=3000,
)
def scrape_actor_stream(self, actor_id, run_input, source="custom", profile_ids=None):
    """Scrape one Apify actor and process each job as it arrives.

    For each item: save to DB → format via GPT → rank against each profile.
    Returns a summary dict when done.
    """
    from apify_client import ApifyClient
    import requests
    from config import APIFY_API_TOKEN, DJANGO_API_URL

    if profile_ids is None:
        profile_ids = []

    client = ApifyClient(APIFY_API_TOKEN)
    persister = DjangoPersistence()
    system_prompt = _get_system_prompt()
    profiles = _get_profiles()

    # Filter to only the requested profiles
    if profile_ids:
        profiles = [p for p in profiles if p.get("id") in profile_ids]

    total_saved = 0
    total_formatted = 0
    total_ranked = 0
    errors = 0

    print(f"   -> Starting actor {actor_id} (streaming per-item)...")

    try:
        run = client.actor(actor_id).start(run_input=run_input)
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]

        for item in poll_items(client, run_id, dataset_id):
            # Sentinel: _done key means the generator is signaling completion
            if isinstance(item, dict) and item.get("_done"):
                continue

            try:
                # Step 1: Save raw job to DB
                job_dict, save_result = clean_and_save_item(item, persister, source=source)
                total_saved += 1

                # Step 2: Format via GPT (in-process, no Celery dispatch)
                raw_data = job_dict.get("raw_data", {})
                try:
                    from persistence import JobFormatter
                    formatter = JobFormatter()
                    input_json = raw_data
                    result = formatter.format_job(input_json)
                    result.setdefault("title", job_dict.get("title", "Unknown"))
                    result.setdefault("company", job_dict.get("company", "Unknown"))
                    result.setdefault("url", job_dict.get("url", ""))
                    result.setdefault("source", job_dict.get("source", "custom"))
                    result.setdefault("salary", "")
                    result.setdefault("description", "")
                    result.setdefault("full_description", "")
                    result.setdefault("tech_stack", [])
                    result.setdefault("language", "EN")
                    result.setdefault("experience_required", "")
                    if raw_data:
                        result["raw_data"] = raw_data
                    result["is_formatted"] = True
                    persister.save_jobs([result])
                    total_formatted += 1
                except Exception as exc:
                    logger.warning("format_failed", extra={
                        "url": job_dict.get("url", ""), "error": str(exc),
                    })

                # Step 3: Fetch the formatted job from DB
                try:
                    resp = requests.get(
                        f"{DJANGO_API_URL}/api/jobs/",
                        params={"search": job_dict.get("url", "")},
                        timeout=10,
                    )
                    db_result = resp.json()
                    if isinstance(db_result, dict) and "results" in db_result:
                        db_result = db_result["results"]
                    formatted_job = db_result[0] if db_result else None
                except Exception:
                    formatted_job = None

                if not formatted_job:
                    continue

                # Step 4: Rank against each profile using formatted data
                for profile in profiles:
                    pid = profile.get("id", "unknown")
                    result = rank_single_job(formatted_job, profile, system_prompt)
                    if result:
                        tier, jd_summary = result
                        try:
                            requests.post(
                                f"{DJANGO_API_URL}/api/rankings/bulk_create/",
                                json=[{
                                    "job_id": formatted_job["id"],
                                    "profile_id": pid,
                                    "profile_title": profile.get("title", pid),
                                    "match_tier": tier,
                                    "rank": 0,
                                    "jd_summary": jd_summary,
                                }],
                                timeout=10,
                            )
                            total_ranked += 1
                        except Exception as exc:
                            logger.warning("ranking_persist_failed", extra={
                                "url": job_dict.get("url", ""), "error": str(exc),
                            })
                    else:
                        logger.warning("rank_single_returned_none", extra={
                            "url": job_dict.get("url", ""), "profile_id": pid,
                        })

            except Exception as exc:
                errors += 1
                logger.error("item_process_failed", extra={
                    "actor_id": actor_id, "error": str(exc),
                })

        print(f"   ✅ Actor {actor_id}: {total_saved} saved, "
              f"{total_formatted} formatted, {total_ranked} ranked")

    except Exception as exc:
        print(f"   ❌ Error executing actor {actor_id}: {exc}")
        return {
            "actor_id": actor_id, "source": source,
            "total_saved": total_saved, "total_formatted": total_formatted,
            "total_ranked": total_ranked, "errors": errors,
            "status": "error",
        }

    return {
        "actor_id": actor_id, "source": source,
        "total_saved": total_saved, "total_formatted": total_formatted,
        "total_ranked": total_ranked, "errors": errors,
        "status": "done",
    }


@app.task(name='tasks.pipeline.send_discord_summary')
def send_discord_summary(scrape_results):
    """Chord callback: all 4 scrapers done. Send Discord summary."""
    from config import DISCORD_WEBHOOK_URL
    import requests as req

    total_saved = sum(r.get("total_saved", 0) for r in scrape_results if r)
    total_ranked = sum(r.get("total_ranked", 0) for r in scrape_results if r)
    sources = {}
    for r in scrape_results:
        if r:
            src = r.get("source", "unknown")
            sources[src] = sources.get(src, 0) + r.get("total_saved", 0)

    print(f"\n📊 Pipeline complete: {total_saved} jobs scraped, {total_ranked} ranked")
    for src, count in sources.items():
        print(f"   {src}: {count} jobs")

    # Send Discord summary
    if DISCORD_WEBHOOK_URL:
        try:
            source_lines = "\n".join(f"  - {src}: {count}" for src, count in sources.items())
            content = (
                f"✅ **Pipeline Complete**\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"{'-'*40}\n"
                f"Jobs scraped: **{total_saved}**\n"
                f"Jobs ranked: **{total_ranked}**\n\n"
                f"**By source:**\n{source_lines}"
            )
            req.post(DISCORD_WEBHOOK_URL, json={"content": content})
            print("   -> Discord summary sent.")
        except Exception as e:
            print(f"   -> Discord send failed: {e}")
    else:
        print("   -> Discord webhook not configured, skipping.")

    # Also send S/A ranked jobs via the existing method
    try:
        ExportHandler.post_tiered_jobs_from_api()
    except Exception as e:
        print(f"   -> S/A Discord post failed: {e}")

    return {"status": "done", "total_saved": total_saved}


@app.task(name='tasks.pipeline.run_pipeline')
def run_pipeline(actor_configs, profile_ids):
    """Entry point: dispatch 4 parallel scraping+formatting+ranking tasks.

    Each scrape_actor_stream task:
      1. Starts one Apify actor
      2. Polls for items as they arrive
      3. For each item: save → format → rank
      4. Returns summary

    When all 4 finish, send_discord_summary fires.
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
