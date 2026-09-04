"""Thin LLM call helper.

`chat_completion()` calls the single configured OpenAI-compatible provider
(base_url from OPENAI_BASE_URL / the settings endpoint) and, if the call
fails, retries up to 3 times against that SAME base_url with a different
API key from the configured pool (OPENAI_API_KEYS plus any
OPENAI_FALLBACK_API_KEY(S) entries — those are just extra keys in the same
pool, not a separate provider). There is no separate fallback provider /
base_url; the "fallback" naming refers only to backup keys.

Keys are sampled WITHOUT replacement, bounded by pool size, so the 3 attempts
never burn their whole budget retrying the same dead key (a pool smaller than
3 just makes fewer attempts instead of repeating one). A key that fails with
an auth error (401/403 — openai.AuthenticationError / PermissionDeniedError)
is put in a short in-process cooldown and skipped by later calls; any other
failure (rate limits, the LLMResponseError shape guard below, timeouts, ...)
does not affect a key's eligibility. Cooldown state is per-process (Celery
prefork workers don't share memory) and keyed by a non-reversible digest of
the key, never the key itself or a list index, since the pool's size and
order can change between calls.

Returns the assistant message content (str). Raises the last exception seen
once all attempts are exhausted.
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time

from openai import AuthenticationError, OpenAI, PermissionDeniedError

from config import (
    get_openai_api_keys,
    get_openai_base_url,
    get_openai_model,
)

logger = logging.getLogger(__name__)

# How long a key that just failed auth is skipped for. Simple in-process
# cooldown — no external datastore, so it resets per worker process and per
# deploy, which is an acceptable tradeoff for a homelab-scale pool.
_AUTH_COOLDOWN_SECONDS = 300

# key digest -> time.monotonic() deadline until which the key is skipped.
_auth_cooldown_lock = threading.Lock()
_auth_cooldown_until: dict[str, float] = {}


def _key_digest(api_key):
    """Short, non-reversible identifier for a key — safe to log or store."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def _is_cooling_down(api_key):
    digest = _key_digest(api_key)
    now = time.monotonic()
    with _auth_cooldown_lock:
        deadline = _auth_cooldown_until.get(digest)
        if deadline is None:
            return False
        if deadline <= now:
            # Expired — clean it up so the dict doesn't grow unbounded.
            del _auth_cooldown_until[digest]
            return False
        return True


def _start_cooldown(api_key):
    digest = _key_digest(api_key)
    with _auth_cooldown_lock:
        _auth_cooldown_until[digest] = time.monotonic() + _AUTH_COOLDOWN_SECONDS


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
    message = choices[0].message
    content = message.content
    if content is None:
        # OpenRouter routinely returns choices[0].message.content == None for
        # reasoning models that put their text in `message.reasoning`
        # instead, for refusals, and for upstream providers that ignore
        # response_format={"type": "json_object"}. Returning None here would
        # let it flow into json.loads(None) downstream (ranking/persistence),
        # which raises TypeError — not json.JSONDecodeError — and either
        # escapes retry handling entirely or gets silently absorbed into a
        # fallback path that marks the job formatted without ever having
        # been formatted. Raise here instead so it stays inside the
        # Exception type chat_completion's own retry loop already catches.
        had_reasoning = getattr(message, "reasoning", None) is not None
        raise LLMResponseError(
            f"LLM provider returned a choice with no message content "
            f"(content is None): response_id={getattr(resp, 'id', None)!r} "
            f"had_reasoning={had_reasoning!r}"
        )
    return content


def chat_completion(messages, temperature=0.2, timeout=120, response_format=None):
    """Run a chat completion, trying up to 3 distinct keys from the pool.

    Keys currently in their auth-failure cooldown are excluded before
    sampling (falling back to the full pool if every key happens to be
    cooling down, rather than failing outright).
    """
    api_keys = get_openai_api_keys()
    if not api_keys:
        raise ValueError("No OpenAI API keys configured.")
    # config.get_openai_api_keys() only dedupes *across* its separate
    # sources (OPENAI_API_KEYS vs OPENAI_API_KEY vs the fallback vars); it
    # does not dedupe *within* a single comma-separated OPENAI_API_KEYS
    # value. random.sample() below samples by position, so a key pasted
    # twice in that list occupies two positions and can be sampled twice,
    # reintroducing the "same key on both attempts" failure this rotation
    # scheme exists to prevent. Dedupe here, preserving order, before any
    # sampling or cooldown filtering happens.
    api_keys = list(dict.fromkeys(api_keys))

    base_url = get_openai_base_url()
    model = get_openai_model()

    available_keys = [k for k in api_keys if not _is_cooling_down(k)]
    if not available_keys:
        available_keys = api_keys

    attempt_keys = random.sample(available_keys, k=min(3, len(available_keys)))

    last_exc = None
    for attempt, api_key in enumerate(attempt_keys):
        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            if attempt > 0:
                logger.info("llm_trying_again", extra={"attempt": attempt + 1})
            return _call(client, model, messages, temperature, timeout, response_format)
        except (AuthenticationError, PermissionDeniedError) as exc:
            _start_cooldown(api_key)
            logger.warning(
                "llm_call_failed_auth_cooldown",
                extra={
                    "error": str(exc),
                    "attempt": attempt + 1,
                    "key_index": attempt,
                    "key_digest": _key_digest(api_key),
                },
            )
            last_exc = exc
            if attempt < len(attempt_keys) - 1:
                time.sleep(1)
            continue
        except Exception as exc:
            logger.warning(
                "llm_call_failed",
                extra={
                    "error": str(exc),
                    "attempt": attempt + 1,
                    "key_index": attempt,
                    "key_digest": _key_digest(api_key),
                },
            )
            last_exc = exc
            if attempt < len(attempt_keys) - 1:
                time.sleep(1)
            continue

    logger.error("llm_all_attempts_failed", extra={"last_error": str(last_exc)})
    raise last_exc
