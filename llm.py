"""Thin LLM call helper with an optional fallback provider.

`chat_completion()` tries the primary OpenAI-compatible provider and, if it
errors, transparently retries against a configured fallback (e.g. a local Ollama
instance). The fallback is disabled by default (empty base_url) so existing
deployments are unaffected until it's explicitly configured via the settings
endpoint / env (OPENAI_FALLBACK_BASE_URL, OPENAI_FALLBACK_MODEL, ...).

Returns the assistant message content (str). Raises the primary exception only
when no fallback is configured or the fallback also fails.
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


def _call(client, model, messages, temperature, timeout, response_format):
    kwargs = dict(model=model, messages=messages, temperature=temperature, timeout=timeout)
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


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
