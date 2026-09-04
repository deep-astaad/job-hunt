"""Thin LLM call helper.

`chat_completion()` calls the single configured OpenAI-compatible provider
(base_url from OPENAI_BASE_URL / the settings endpoint) and, if the call
fails, retries up to 3 times against that SAME base_url with a different
randomly-chosen API key from the configured pool (OPENAI_API_KEYS plus any
OPENAI_FALLBACK_API_KEY(S) entries — those are just extra keys in the same
pool, not a separate provider). There is no separate fallback provider /
base_url; the "fallback" naming refers only to backup keys.

Returns the assistant message content (str). Raises the last exception seen
once all attempts are exhausted.
"""
from __future__ import annotations

import logging

from openai import OpenAI

from config import (
    get_openai_api_keys,
    get_openai_base_url,
    get_openai_model,
)

logger = logging.getLogger(__name__)


class LLMResponseError(Exception):
    """Raised when the provider returns a 200 with no usable choices.

    OpenRouter (and other OpenAI-compatible providers) do this for rate
    limiting, free-tier throttling, and upstream model errors: the HTTP call
    succeeds but the body is error-shaped (`choices` missing/None/empty, an
    `error` field instead). Indexing that response directly raises an opaque
    `TypeError: 'NoneType' object is not subscriptable`, which is neither an
    `openai.*` exception nor a `requests.RequestException` and therefore
    escapes both retry ladders in tasks/ranking.py, permanently failing the
    job. Raising this instead keeps the failure inside the `Exception` type
    that chat_completion's own retry loop already catches, and carries the
    provider's error payload so it's visible in logs.
    """


def _call(client, model, messages, temperature, timeout, response_format):
    kwargs = dict(model=model, messages=messages, temperature=temperature, timeout=timeout)
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    choices = getattr(resp, "choices", None)
    if not choices:
        error_payload = getattr(resp, "error", None)
        raise LLMResponseError(
            f"LLM provider returned no choices (error-shaped response): "
            f"error={error_payload!r} response_id={getattr(resp, 'id', None)!r}"
        )
    return choices[0].message.content


def chat_completion(messages, temperature=0.2, timeout=120, response_format=None):
    """Run a chat completion randomly picking an API key from the pool, with up to 3 retries."""
    api_keys = get_openai_api_keys()
    if not api_keys:
        raise ValueError("No OpenAI API keys configured.")
        
    base_url = get_openai_base_url()
    model = get_openai_model()
    
    import random
    import time

    last_exc = None
    for attempt in range(3):
        api_key = random.choice(api_keys)
        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            if attempt > 0:
                logger.info("llm_trying_again", extra={"attempt": attempt + 1})
            return _call(client, model, messages, temperature, timeout, response_format)
        except Exception as exc:
            logger.warning("llm_call_failed", extra={"error": str(exc), "attempt": attempt + 1})
            last_exc = exc
            if attempt < 2:
                time.sleep(1)
            continue
            
    logger.error("llm_all_attempts_failed", extra={"last_error": str(last_exc)})
    raise last_exc
