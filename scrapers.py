import json
from apify_client import ApifyClient
from config import APIFY_API_TOKEN

class JobScraperPipeline:
    def __init__(self):
        self.client = ApifyClient(APIFY_API_TOKEN)

    def load_json_file(self, filepath):
        with open(filepath, 'r') as f:
            return json.load(f)

    def run_all_actors(self, config_path="actor-config.json"):
        """Iterates through actor-config.json and aggregates all listing payloads."""
        actor_configs = self.load_json_file(config_path)
        aggregated_jobs = []

        print("\n🕸️  Phase 1: Scraping Data via Apify")
        for config in actor_configs:
            actor_id = config["actor_id"]
            run_input = config["input"]
            print(f"   -> Starting actor {actor_id}...")
            
            try:
                run = self.client.actor(actor_id).call(run_input=run_input)
                dataset_items = self.client.dataset(run["defaultDatasetId"]).list_items().items
                print(f"   ✅ Fetched {len(dataset_items)} job listings from {actor_id}")
                aggregated_jobs.extend(dataset_items)
            except Exception as e:
                print(f"   ❌ Error executing actor {actor_id}: {e}")

        return aggregated_jobs

    def clean_payload(self, raw_jobs):
        """Standardizes dynamic keys across multiple distinct community scrapers."""
        minimized_jobs = []
        for job in raw_jobs:
            minimized_jobs.append({
                "title": job.get("title", job.get("position", "Unknown")),
                "company": job.get("company", "Unknown"),
                "url": job.get("url", job.get("jobUrl", "Unknown")),
                "salary": job.get("salary", "Not listed"),
                "description": str(job.get("description", ""))[:1500]  # Cap length for token budgeting
            })
        print(f"🧹 Phase 2: Flattened and cleaned {len(minimized_jobs)} job objects.")
        return minimized_jobs