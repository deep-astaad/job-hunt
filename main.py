import os
import json
from dotenv import load_dotenv
from apify_client import ApifyClient
from openai import OpenAI

# 1. Load environment variables
load_dotenv()
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not APIFY_API_TOKEN or not OPENAI_API_KEY:
    print("❌ ERROR: Missing API keys. Please check your .env file.")
    exit(1)

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    print("🚀 Initializing Job Scraper & AI Ranker Pipeline...")
    
    apify_client = ApifyClient(APIFY_API_TOKEN)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    actor_configs = load_json("actor-config.json")
    profiles = load_json("user-profiles.json")
    
    with open("system-prompt.txt", "r") as f:
        system_prompt = f.read()

    all_jobs = []

    # 2. Run Apify Actors and Aggregate Data
    print("\n🕸️  Phase 1: Scraping Data via Apify")
    for config in actor_configs:
        actor_id = config["actor_id"]
        run_input = config["input"]
        print(f"   -> Starting actor {actor_id} (This may take a minute)...")
        
        run = apify_client.actor(actor_id).call(run_input=run_input)
        dataset_items = apify_client.dataset(run["defaultDatasetId"]).list_items().items
        
        print(f"   ✅ Fetched {len(dataset_items)} job listings from {actor_id}")
        all_jobs.extend(dataset_items)

    if not all_jobs:
        print("❌ No jobs found. Exiting.")
        return

    # 3. Clean and prepare data for OpenAI
    print("\n🧹 Phase 2: Cleaning Data (Minimizing payload)")
    minimized_jobs = []
    for i, job in enumerate(all_jobs):
        minimized_jobs.append({
            "title": job.get("title", job.get("position", "Unknown")),
            "company": job.get("company", "Unknown"),
            "url": job.get("url", job.get("jobUrl", "Unknown")),
            "salary": job.get("salary", "Not listed"),
            # Truncate description to 1500 chars to avoid hitting LLM token limits
            "description": str(job.get("description", ""))[:1500] 
        })

    # Choose a profile to match against (Defaulting to the first one: Backend)
    selected_profile = profiles[0]
    print(f"   -> Matching jobs against profile: {selected_profile['title']}")

    user_content = f"CANDIDATE PROFILE:\n{json.dumps(selected_profile, indent=2)}\n\nJOB DATA:\n{json.dumps(minimized_jobs, indent=2)}"

    # 4. Call OpenAI to rank and summarize
    print("\n🧠 Phase 3: Analyzing and Ranking via OpenAI (gpt-4o-mini)")
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.2 # Keep it analytical and deterministic
    )

    result_markdown = response.choices[0].message.content

    print("\n" + "="*70 + "\n")
    print(result_markdown)
    print("\n" + "="*70 + "\n")

    # 5. Save output
    output_filename = "ranked_jobs_output.md"
    with open(output_filename, "w", encoding='utf-8') as f:
        f.write(f"# AI Ranked Job Listings\n\n**Profile matched:** {selected_profile['title']}\n\n")
        f.write(result_markdown)
        
    print(f"💾 Success! Ranked results saved to {output_filename}")

if __name__ == "__main__":
    main()
