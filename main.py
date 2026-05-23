import os
from datetime import datetime
from scrapers import JobScraperPipeline
from ranker import JobRankerAI
from persistence import JobFormatter, DjangoPersistence
from outputs import ExportHandler

PROFILE_IDS = ["backend_dev", "cloud_infra"]

def main():
    print("🚀 Booting Modularized SDE Job Aggregator Engine...")

    # 1. Scrape raw data from Apify actors (no cleaning)
    scraper = JobScraperPipeline()
    raw_data = scraper.run_all_actors()

    if not raw_data:
        print("❌ Scrapers returned empty blocks. Terminating execution workflow loop.")
        return

    print(f"🧹 Phase 2: Received {len(raw_data)} raw job listings from scrapers.")

    # 2. Format each raw job via gpt-4o-mini (1 at a time) into Job model shape
    formatter = JobFormatter()
    formatted_jobs = formatter.format_all(raw_data)

    if not formatted_jobs:
        print("❌ No jobs formatted. Terminating.")
        return

    # 3. Save formatted jobs to Django DB
    persister = DjangoPersistence()
    persister.persist_jobs(formatted_jobs)

    # 4. Fetch jobs back from DB and rank them
    db_jobs = persister.fetch_jobs_today()
    if not db_jobs:
        print("⚠️ No jobs found in DB. Skipping ranking.")
        return

    # 5. Rank for each profile
    ai_engine = JobRankerAI()

    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    time_str = current_time.strftime("%H%M%S")
    target_directory = os.path.join("data", date_str)
    os.makedirs(target_directory, exist_ok=True)

    for profile_id in PROFILE_IDS:
        print(f"\n📊 Ranking for profile: {profile_id}")
        markdown_result, profile_title = ai_engine.generate_rankings(db_jobs, profile_id=profile_id)

        # Save rankings to Django DB
        persister.save_rankings(markdown_result, profile_id, profile_title, db_jobs)

        # Save Markdown report
        suffix = f"_{profile_id}" if len(PROFILE_IDS) > 1 else ""
        md_output_path = os.path.join(target_directory, f"{time_str}{suffix}.md")
        csv_output_path = os.path.join(target_directory, f"{time_str}{suffix}.csv")

        with open(md_output_path, "w", encoding="utf-8") as f:
            f.write(markdown_result)
        print(f"💾 Markdown report saved to: {md_output_path}")

        # Generate side-effects (CSV Conversion and Discord Notification)
        ExportHandler.parse_markdown_table_to_csv(markdown_result, csv_output_path)
        # ExportHandler.post_embeds_to_discord(markdown_result, profile_title)

    print(f"\n🏁 Process Finished. Historical run recorded under: {target_directory}/")

if __name__ == "__main__":
    main()