import os
from datetime import datetime
from scrapers import JobScraperPipeline
from ranker import JobRankerAI
from persistence import JobFormatter, DjangoPersistence
from outputs import ExportHandler

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

    ai_engine = JobRankerAI()
    markdown_result, profile_title = ai_engine.generate_rankings(db_jobs, profile_id="backend_dev")

    # 5. Save rankings to Django DB
    persister.save_rankings(markdown_result, "backend_dev", profile_title, db_jobs)

    # 6. Dynamic Path Resolution: /data/{date}/{time}
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")    # Generates folder name (e.g., 2026-05-22)
    time_str = current_time.strftime("%H%M%S")       # Generates filename (e.g., 183025)

    # Ensure the target nested directory paths exist locally
    target_directory = os.path.join("data", date_str)
    os.makedirs(target_directory, exist_ok=True)

    # Construct the final specific paths
    md_output_path = os.path.join(target_directory, f"{time_str}.md")
    csv_output_path = os.path.join(target_directory, f"{time_str}.csv")

    # 7. Save Markdown report
    with open(md_output_path, "w", encoding="utf-8") as f:
        f.write(markdown_result)
    print(f"💾 Markdown report saved to: {md_output_path}")

    # 8. Generate side-effects (CSV Conversion and Discord Notification)
    ExportHandler.parse_markdown_table_to_csv(markdown_result, csv_output_path)
    # ExportHandler.post_embeds_to_discord(markdown_result, profile_title)
    
    print(f"\n🏁 Process Finished. Historical run recorded under: {target_directory}/")

if __name__ == "__main__":
    main()