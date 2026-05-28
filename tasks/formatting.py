import logging

import openai
from celery_app import app
from persistence import JobFormatter, DjangoPersistence

logger = logging.getLogger(__name__)

_formatter = JobFormatter()


def _fallback_from_raw(job_data):
    """Build a minimal job dict from raw data when GPT formatting fails."""
    raw_data = job_data.get("raw_data", {})
    return {
        "title": job_data.get("title", "Unknown"),
        "company": job_data.get("company", "Unknown"),
        "url": job_data.get("url", ""),
        "source": job_data.get("source", "custom"),
        "salary": job_data.get("salary", "") or "",
        "description": str(job_data.get("description", "")),
        "full_description": str(job_data.get("full_description", "")),
        "tech_stack": [],
        "language": "",
        "experience_required": "",
        "raw_data": raw_data,
        "is_formatted": True,
    }


@app.task(
    bind=True,
    name='tasks.formatting.format_and_persist_job',
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,
)
def format_and_persist_job(self, job_data):
    """Format a DB job via GPT and update the record.

    Returns the formatted job dict (with id) on success, False on failure.
    The linked ranking task receives this return value.
    """
    persister = DjangoPersistence()
    job_id = job_data.get("id")
    raw_data = job_data.get("raw_data")
    input_json = raw_data or job_data

    try:
        import os
        import time
        if os.getenv("MOCK_LLM") == "1":
            time.sleep(1)  # Simulate API latency
            raise Exception("Mocking LLM fallback")
        result = _formatter.format_job(input_json)
    except (openai.RateLimitError, openai.APIError, openai.APITimeoutError) as exc:
        if os.getenv("MOCK_LLM") == "1":
            result = _fallback_from_raw(job_data)
        else:
            logger.warning("format_gpt_retry", extra={
                "job_id": job_id, "attempt": self.request.retries, "error": str(exc),
            })
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
    except Exception as exc:
        logger.warning("format_gpt_fallback", extra={
            "job_id": job_id, "error": str(exc),
        })
        result = _fallback_from_raw(job_data)

    from persistence import detect_job_language
    result.setdefault("title", job_data.get("title", "Unknown"))
    result.setdefault("company", job_data.get("company", "Unknown"))
    result.setdefault("url", job_data.get("url", ""))
    result.setdefault("source", job_data.get("source", "custom"))
    result.setdefault("salary", "")
    result.setdefault("description", "")
    result.setdefault("full_description", "")
    result.setdefault("tech_stack", [])
    result.setdefault("language", "EN")
    result["language"] = detect_job_language(result)
    result.setdefault("experience_required", "")

    if raw_data:
        result["raw_data"] = raw_data
    result["is_formatted"] = True

    try:
        if job_id:
            updated = persister.update_job(job_id, result)
            return updated
        else:
            persister.save_jobs([result])
            return result
    except Exception as exc:
        logger.error("format_persist_failed", extra={
            "job_id": job_id, "error": str(exc),
        })
        return False
