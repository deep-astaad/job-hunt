import logging

import openai
import requests
from celery_app import app
from llm import LLMResponseError
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
    """Build a minimal job dict from raw data when GPT formatting fails.

    Issue #125d fix 2: this used to hardcode `is_formatted: True`. A scraper
    stub (tasks/pipeline.py's _extract_job_dict) always sets description and
    full_description to "" - the real text lives only in raw_data - so this
    fallback almost always produces a content-free dict. Marking that
    is_formatted=True froze it as "done": the ranker then honestly scores an
    empty "Full Job Description:" as F, is_ranked flips True, and the job is
    never reformatted or reranked again. The branch's own acceptance sample
    found empty-description jobs F'd at 83.3% vs 46.9% for jobs with real
    content - this path was manufacturing the worst case. is_formatted is no
    longer set here; the caller decides it based on whether the merged
    result actually has usable content.
    """
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
    # Issue #125 part 3: one LLM call per job. Celery's rate_limit is enforced
    # once per Consumer (the single `celery worker` process/replica that reads
    # off the broker), NOT per pool execution slot - confirmed by reading the
    # installed celery==5.6.3 source (uv.lock resolves 5.6.3, not 5.4;
    # celery/worker/strategy.py's `bucket = get_bucket(task.name)` and
    # consumer.py's `bucket_for_task`/`_limit_task`, which build one
    # TokenBucket per task name off `type.rate_limit` and gate hand-off into
    # the pool via the Consumer's own timer, are unchanged between those
    # versions). So --concurrency=4 (deploy/celery-worker.yaml,
    # --pool=threads) does NOT multiply this: it only bounds how many
    # already-released tasks may run in parallel, not how fast new ones are
    # released. What DOES multiply it is deploy replica count (each replica
    # runs its own Consumer/bucket, uncoordinated) - celery-worker is
    # `replicas: 1`, so this cap is the real aggregate cap today. See
    # rank_job_multi_profile's rate_limit for the sibling half of the
    # budget - the two sum to 20 task releases/min, since each job costs one
    # format call + one ranking call. That is NOT the same as upstream HTTP
    # request volume: llm.py's chat_completion does
    # `random.sample(available_keys, k=min(3, len(available_keys)))`, so one
    # task can make up to 3 requests against the key pool. Healthy path is
    # ~20 req/min (1 request/task, matches observed evidence); a degraded
    # path where most calls need key rotation can reach ~60 upstream
    # requests/min.
    rate_limit='10/m',
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

    used_fallback = False
    try:
        import os
        import time
        if os.getenv("MOCK_LLM") == "1":
            time.sleep(1)  # Simulate API latency
            raise Exception("Mocking LLM fallback")
        result = _formatter.format_job(input_json)
    # Issue #125d fix 2: LLMResponseError is included here now. llm.py's
    # chat_completion raises it when the provider returns an error-shaped
    # HTTP 200 (rate limiting / free-tier throttling signalled without a
    # non-2xx status - see llm.py's module docstring). It used to fall
    # through to the bare `except Exception` below, which fabricates a
    # content-free "formatted" job instead of retrying the throttle away.
    except (openai.RateLimitError, openai.APIError, openai.APITimeoutError, LLMResponseError) as exc:
        if os.getenv("MOCK_LLM") == "1":
            result = _fallback_from_raw(job_data)
            used_fallback = True
        else:
            logger.warning("format_gpt_retry", extra={
                "job_id": job_id, "attempt": self.request.retries, "error": str(exc),
            })
            # Issue #125d fix 1: route through _retry_or_release instead of
            # calling self.retry directly. Celery's Task.retry on exhaustion
            # does raise_with_context(exc), so the original exception used to
            # propagate straight out of this task, skipping
            # _release_processing_state entirely - the job_processing_lock
            # was never deleted. Since commit 4029b56 the pipeline heartbeat
            # refreshes any lock it finds still held on every beat run, so a
            # leaked lock is now refreshed forever instead of expiring off
            # its 1h TTL: the job is stranded permanently, not just delayed.
            # _retry_or_release keeps this branch's existing backoff
            # (30 * 2**retries) for the non-exhausted case and releases the
            # lock before re-raising once retries are exhausted - matching
            # what tasks/ranking.py's sibling branch already does (8bdf9d3).
            _retry_or_release(self, exc, job_id, pipeline_run_id)
    except Exception as exc:
        logger.warning("format_gpt_fallback", extra={
            "job_id": job_id, "error": str(exc),
        })
        result = _fallback_from_raw(job_data)
        used_fallback = True

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

    # Issue #125d fix 2: only claim is_formatted when the LLM path actually
    # produced the result, or the fallback happened to land on real content.
    # A fallback with no usable description/full_description is left
    # is_formatted=False so process_unprocessed_jobs_task's backlog scan
    # (filters on is_formatted=False) retries this job on a later pass
    # instead of freezing a content-free row the ranker can only ever F.
    has_content = bool(str(result.get("description") or "").strip()) or bool(
        str(result.get("full_description") or "").strip()
    )
    result["is_formatted"] = (not used_fallback) or has_content

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
