from celery_app import app
from apify_client import ApifyClient
from config import APIFY_API_TOKEN
from scrapers import JobScraperPipeline


@app.task(
    bind=True,
    name='tasks.scraping.scrape_actor',
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=600,
)
def scrape_actor(self, actor_id, run_input):
    """Run a single Apify actor and return cleaned raw job dicts."""
    client = ApifyClient(APIFY_API_TOKEN)
    pipeline = JobScraperPipeline()

    try:
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
        cleaned = pipeline.clean_payload(dataset_items)
        print(f"  Scraped {len(cleaned)} jobs from {actor_id}")
        return cleaned
    except Exception as exc:
        print(f"  Error scraping {actor_id}: {exc}")
        raise self.retry(exc=exc)
