import os
from datetime import datetime
from scrapers import JobScraperPipeline
from ranker import JobRankerAI
from outputs import ExportHandler

def main():
    print("🚀 Booting Modularized SDE Job Aggregator Engine...")
    
    # 1. Scraping and formatting step
    scraper = JobScraperPipeline()
    raw_data = scraper.run_all_actors()
    
    if not raw_data:
        print("❌ Scrapers returned empty blocks. Terminating execution workflow loop.")
        return
        
    cleaned_data = scraper.clean_payload(raw_data)

    # 2. Match Grading evaluation 
    ai_engine = JobRankerAI()
    # Note: Swap "backend_dev" to "cloud_infra" to test your alternative json conditions
    markdown_result, profile_title = ai_engine.generate_rankings(cleaned_data, profile_id="backend_dev")

    # 3. Dynamic Path Resolution: /data/{date}/{time}
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")    # Generates folder name (e.g., 2026-05-22)
    time_str = current_time.strftime("%H%M%S")       # Generates filename (e.g., 183025)

    # Ensure the target nested directory paths exist locally
    target_directory = os.path.join("data", date_str)
    os.makedirs(target_directory, exist_ok=True)

    # Construct the final specific paths
    md_output_path = os.path.join(target_directory, f"{time_str}.md")
    csv_output_path = os.path.join(target_directory, f"{time_str}.csv")

    # 4. Save Markdown report
    with open(md_output_path, "w", encoding="utf-8") as f:
        f.write(markdown_result)
    print(f"💾 Markdown report saved to: {md_output_path}")

    # 5. Generate side-effects (CSV Conversion and Discord Notification)
    ExportHandler.parse_markdown_table_to_csv(markdown_result, csv_output_path)
    ExportHandler.post_embeds_to_discord(markdown_result, profile_title)
    
    print(f"\n🏁 Process Finished. Historical run recorded under: {target_directory}/")

if __name__ == "__main__":
    main()