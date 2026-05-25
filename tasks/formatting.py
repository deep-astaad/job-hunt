from celery_app import app
from persistence import JobFormatter, DjangoPersistence

_formatter = JobFormatter()


@app.task(
    bind=True,
    name='tasks.formatting.format_and_persist_job',
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
)
def format_and_persist_job(self, job_data):
    """Format a DB job via LLM and update the record with is_formatted=True.

    Receives a job dict from the DB (fetched by scrape_all_actors).
    If raw_data (full Apify JSON) is present, it's sent to GPT for formatting.
    """
    persister = DjangoPersistence()
    job_id = job_data.get("id")

    raw_data = job_data.get("raw_data")
    input_json = raw_data or job_data

    try:
        result = _formatter.format_job(input_json)
        result.setdefault("title", job_data.get("title", "Unknown"))
        result.setdefault("company", job_data.get("company", "Unknown"))
        result.setdefault("url", job_data.get("url", ""))
        result.setdefault("source", job_data.get("source", "custom"))
        result.setdefault("salary", "")
        result.setdefault("description", "")
        result.setdefault("full_description", "")
        result.setdefault("tech_stack", [])
        result.setdefault("language", "EN")
        result.setdefault("experience_required", "")

    except Exception as exc:
        print(f"  LLM formatting failed, using raw fallback: {exc}")
        result = {
            "title": job_data.get("title", "Unknown"),
            "company": job_data.get("company", "Unknown"),
            "url": job_data.get("url", ""),
            "source": job_data.get("source", "custom"),
            "salary": job_data.get("salary", ""),
            "description": str(job_data.get("description", ""))[:500],
            "full_description": str(job_data.get("description", "")),
            "tech_stack": [],
            "language": "EN",
            "experience_required": "",
        }

    # Preserve raw_data only if it was actually Apify data (not the DB record)
    if raw_data:
        result["raw_data"] = raw_data

    # Mark as formatted
    result["is_formatted"] = True

    try:
        if job_id:
            persister.update_job(job_id, result)
        else:
            # Fallback: use bulk_create if no job_id (shouldn't happen in normal flow)
            persister.save_jobs([result])
        return True
    except Exception as exc:
        print(f"  Failed to persist formatted job: {exc}")
        return False
