import logging

import openai
import requests
from celery_app import app
from persistence import JobFormatter, DjangoPersistence

logger = logging.getLogger(__name__)

_formatter = JobFormatter()


def _response_text(exc):
    response = getattr(exc, "response", None)
    text = getattr(response, "text", "")
    return text[:1000] if text else ""


def _is_permanent_http_error(exc):
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code is not None and 400 <= status_code < 500 and status_code != 429


def _release_processing_state(job_id, pipeline_run_id=None):
    if not job_id:
        return
    if pipeline_run_id:
        from tasks.ranking import _check_and_trigger_discord
        _check_and_trigger_discord(pipeline_run_id, job_id)
        return

    try:
        import redis
        from config import CELERY_BROKER_URL
        redis.Redis.from_url(CELERY_BROKER_URL).delete(f"job_processing_lock:{job_id}")
    except Exception as exc:
        logger.error("job_processing_lock_release_failed", extra={
            "job_id": job_id,
            "error": str(exc),
        })


def _retry_or_release(self, exc, job_id, pipeline_run_id):
    if self.request.retries >= self.max_retries:
        _release_processing_state(job_id, pipeline_run_id)
        raise exc
    raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


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


def _fill_required_text(result, key, fallback, default="Unknown"):
    value = result.get(key)
    if isinstance(value, str) and value.strip():
        return
    if value and not isinstance(value, str):
        return

    fallback_value = fallback if isinstance(fallback, str) else ""
    result[key] = fallback_value.strip() or default


@app.task(
    bind=True,
    name='tasks.formatting.format_and_persist_job',
    max_retries=5,
    default_retry_delay=30,
    soft_time_limit=300,
)
def format_and_persist_job(self, job_data):
    """Format a DB job via GPT and update the record.

    Returns the formatted job dict (with id) on success. Persistence failures
    raise/retry so the linked ranking task is not called with missing job data.
    """
    persister = DjangoPersistence()
    job_id = job_data.get("id")
    pipeline_run_id = job_data.get("pipeline_run_id")
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

    from persistence import detect_job_language, detect_job_location
    _fill_required_text(result, "title", job_data.get("title"), "Unknown")
    _fill_required_text(result, "company", job_data.get("company"), "Unknown")
    _fill_required_text(result, "url", job_data.get("url"), "")
    _fill_required_text(result, "source", job_data.get("source"), "custom")
    result.setdefault("salary", "")
    result.setdefault("description", "")
    result.setdefault("full_description", "")
    result.setdefault("tech_stack", [])
    result.setdefault("language", "EN")
    result["language"] = detect_job_language(result)
    result["location"] = detect_job_location(result, raw_data)
    result.setdefault("experience_required", "")

    if raw_data:
        result["raw_data"] = raw_data
    result["is_formatted"] = True

    try:
        if job_id:
            updated = persister.update_job(job_id, result)
            return updated
        persister.save_jobs([result])
        return result
    except requests.HTTPError as exc:
        logger.error("format_persist_failed", extra={
            "job_id": job_id,
            "status_code": getattr(getattr(exc, "response", None), "status_code", None),
            "response_body": _response_text(exc),
            "error": str(exc),
        })
        if _is_permanent_http_error(exc):
            _release_processing_state(job_id, pipeline_run_id)
            raise
        _retry_or_release(self, exc, job_id, pipeline_run_id)
    except requests.RequestException as exc:
        logger.warning("format_persist_retry", extra={
            "job_id": job_id,
            "error": str(exc),
        })
        _retry_or_release(self, exc, job_id, pipeline_run_id)
    except Exception as exc:
        logger.error("format_persist_failed", extra={
            "job_id": job_id,
            "error": str(exc),
        })
        _release_processing_state(job_id, pipeline_run_id)
        raise
