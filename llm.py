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
    get_openai_api_key,
    get_openai_base_url,
    get_openai_model,
    get_openai_fallback_api_key,
    get_openai_fallback_base_url,
    get_openai_fallback_model,
)

logger = logging.getLogger(__name__)


def _call(client, model, messages, temperature, timeout, response_format):
    kwargs = dict(model=model, messages=messages, temperature=temperature, timeout=timeout)
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def chat_completion(messages, temperature=0.2, timeout=120, response_format=None):
    """Run a chat completion with automatic fallback. Returns the content string."""
    primary_client = OpenAI(api_key=get_openai_api_key(), base_url=get_openai_base_url())
    try:
        return _call(primary_client, get_openai_model(), messages,
                     temperature, timeout, response_format)
    except Exception as primary_exc:
        fb_base = get_openai_fallback_base_url()
        if not fb_base:
            raise
        logger.warning("llm_primary_failed_trying_fallback", extra={
            "error": str(primary_exc), "fallback_base_url": fb_base,
        })
        fb_client = OpenAI(api_key=get_openai_fallback_api_key(), base_url=fb_base)
        try:
            return _call(fb_client, get_openai_fallback_model(), messages,
                         temperature, timeout, response_format)
        except Exception as fb_exc:
            logger.error("llm_fallback_also_failed", extra={"error": str(fb_exc)})
            # Surface the original (primary) error to preserve existing retry logic.
            raise primary_exc
