import os
from datetime import datetime
from celery import group, chord
from celery_app import app
from persistence import DjangoPersistence, normalize_url
from ranker import JobRankerAI
from outputs import ExportHandler
from tasks.scraping import scrape_actor
from tasks.formatting import format_and_persist_job
from tasks.ranking import rank_batch


@app.task(name='tasks.pipeline.run_pipeline')
def run_pipeline(actor_configs, profile_ids):
    """Entry point: dispatch parallel scraping via CHORD 1."""
    scrape_group = group(
        scrape_actor.s(config["actor_id"], config["input"])
        for config in actor_configs
    )
    chord(scrape_group)(scrape_all_actors.s(profile_ids=profile_ids))


@app.task(name='tasks.pipeline.scrape_all_actors')
def scrape_all_actors(raw_jobs_lists, profile_ids):
    """CHORD 1 callback: flatten and deduplicate scraped jobs, dispatch formatting."""
    all_raw_jobs = []
    for actor_result in raw_jobs_lists:
        if actor_result:
            all_raw_jobs.extend(actor_result)

    # Deduplicate by normalized URL
    seen = set()
    deduped = []
    for job in all_raw_jobs:
        url = job.get("url", "")
        norm = normalize_url(url)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(job)

    print(f"  {len(deduped)} unique jobs after dedup (from {len(all_raw_jobs)} raw)")

    if not deduped:
        return

    format_group = group(
        format_and_persist_job.s(raw_job)
        for raw_job in deduped
    )
    chord(format_group)(trigger_ranking.s(profile_ids=profile_ids))


@app.task(name='tasks.pipeline.trigger_ranking')
def trigger_ranking(format_results, profile_ids):
    """CHORD 2 callback: fetch today's jobs from DB, dispatch ranking per profile."""
    persister = DjangoPersistence()
    db_jobs = persister.fetch_jobs_today()

    if not db_jobs:
        print("  No jobs found in DB. Skipping ranking.")
        return

    for profile_id in profile_ids:
        batches = [
            db_jobs[i:i + JobRankerAI.BATCH_SIZE]
            for i in range(0, len(db_jobs), JobRankerAI.BATCH_SIZE)
        ]
        print(f"  Dispatching {len(batches)} ranking batches for profile: {profile_id}")
        rank_group = group(
            rank_batch.s(batch, profile_id)
            for batch in batches
        )
        chord(rank_group)(merge_and_export.s(profile_id=profile_id))


@app.task(name='tasks.pipeline.merge_and_export')
def merge_and_export(all_batch_rows, profile_id):
    """CHORD 3 callback: merge batch rankings, persist, export."""
    # Flatten batch results
    all_rows = []
    for batch_rows in all_batch_rows:
        if batch_rows:
            all_rows.extend(batch_rows)

    if not all_rows:
        print(f"  No rankings to merge for {profile_id}.")
        return

    # Load profile info for persistence
    ranker = JobRankerAI()
    profiles = ranker._load_json("user-profiles.json")
    selected_profile = next((p for p in profiles if p["id"] == profile_id), profiles[0])

    # Build markdown table
    header = "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |"
    separator = "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"

    # If multiple batches, merge via LLM
    if len(all_batch_rows) > 1:
        system_prompt = ranker._read_file("system-prompt.txt")

        try:
            merged = ranker._merge_tables(all_rows, selected_profile, system_prompt)
            if "```" in merged:
                merged = merged.split("```")[1] if merged.count("```") >= 2 else merged
                if merged.strip().startswith("markdown"):
                    merged = merged.strip().split("\n", 1)[1] if "\n" in merged else merged
            merged_rows = ranker._parse_ranking_table(merged)
            jobs_by_url = {j["url"]: j for j in db_jobs_all() if j.get("url")}
            merged_rows = ranker._fix_summaries(merged_rows, jobs_by_url)
            rows_str = "\n".join([f"| {'|'.join(r)} |" for r in merged_rows])
            markdown_result = "\n".join([header, separator, rows_str])
        except Exception as exc:
            print(f"  Merge failed: {exc}. Using concatenated tables.")
            rows_str = "\n".join([f"| {'|'.join(r)} |" for r in all_rows])
            markdown_result = "\n".join([header, separator, rows_str])
    else:
        rows_str = "\n".join([f"| {'|'.join(r)} |" for r in all_rows])
        markdown_result = "\n".join([header, separator, rows_str])

    # Persist rankings
    persister = DjangoPersistence()
    db_jobs = persister.fetch_jobs_today()
    profile_title = selected_profile.get("title", profile_id)
    persister.save_rankings(markdown_result, profile_id, profile_title, db_jobs)

    # Save markdown and CSV
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    time_str = current_time.strftime("%H%M%S")
    target_directory = os.path.join("data", date_str)
    os.makedirs(target_directory, exist_ok=True)

    suffix = f"_{profile_id}"
    md_output_path = os.path.join(target_directory, f"{time_str}{suffix}.md")
    csv_output_path = os.path.join(target_directory, f"{time_str}{suffix}.csv")

    with open(md_output_path, "w", encoding="utf-8") as f:
        f.write(markdown_result)

    ExportHandler.parse_markdown_table_to_csv(markdown_result, csv_output_path)
    ExportHandler.post_tiered_jobs_from_api(profile_id=profile_id)

    print(f"  Export complete for {profile_id}. Files saved to {target_directory}/")


def db_jobs_all():
    """Helper to fetch all today's jobs (used for fix_summaries)."""
    persister = DjangoPersistence()
    return persister.fetch_jobs_today()
