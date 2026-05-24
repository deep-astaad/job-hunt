from celery_app import app
from persistence import JobFormatter, DjangoPersistence


@app.task(
    bind=True,
    name='tasks.formatting.format_and_persist_job',
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
)
def format_and_persist_job(self, raw_job):
    """Format a single raw job via LLM and persist to Django DB."""
    formatter = JobFormatter()
    persister = DjangoPersistence()

    try:
        result = formatter.format_job(raw_job)
        result.setdefault("title", raw_job.get("title", "Unknown"))
        result.setdefault("company", raw_job.get("companyName", raw_job.get("company", "Unknown")))
        result.setdefault("url", raw_job.get("link", raw_job.get("url", raw_job.get("applyUrl", ""))))
        result.setdefault("source", "custom")
        result.setdefault("salary", "")
        result.setdefault("description", "")
        result.setdefault("full_description", "")
        result.setdefault("tech_stack", [])
        result.setdefault("language", "EN")
        result.setdefault("experience_required", "")
    except Exception as exc:
        print(f"  LLM formatting failed, using raw fallback: {exc}")
        result = {
            "title": raw_job.get("title", raw_job.get("standardizedTitle", "Unknown")),
            "company": raw_job.get("companyName", raw_job.get("company", "Unknown")),
            "url": raw_job.get("link", raw_job.get("url", raw_job.get("applyUrl", ""))),
            "source": "custom",
            "salary": raw_job.get("salary", ""),
            "description": str(raw_job.get("descriptionText", raw_job.get("description", "")))[:500],
            "full_description": str(raw_job.get("descriptionText", raw_job.get("description", ""))),
            "tech_stack": [],
            "language": "EN",
            "experience_required": "",
        }

    try:
        persister.save_jobs([result])
        return True
    except Exception as exc:
        print(f"  Failed to persist job: {exc}")
        return False
