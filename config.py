import os
import redis

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# Redis client for dynamic settings
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)
        except Exception:
            pass
    return _redis_client

def get_dynamic_setting(key, default_val=None):
    r = get_redis_client()
    if r:
        try:
            val = r.hget("app_settings", key)
            if val is not None:
                return val
        except Exception:
            pass
    return os.getenv(key, default_val)

def get_apify_api_token():
    return get_dynamic_setting("APIFY_API_TOKEN")

def get_openai_api_key():
    return get_dynamic_setting("OPENAI_API_KEY")

def get_openai_base_url():
    return get_dynamic_setting("OPENAI_BASE_URL", "https://api.openai.com/v1")

def get_openai_model():
    return get_dynamic_setting("OPENAI_MODEL", "gpt-4o-mini")


# --- Fallback LLM provider (e.g. a local Ollama instance) ---
# Used only when the primary provider errors out. Empty base_url => disabled, so
# existing deployments behave exactly as before until explicitly configured.
def get_openai_fallback_base_url():
    return get_dynamic_setting("OPENAI_FALLBACK_BASE_URL", "")

def get_openai_fallback_api_key():
    # Ollama ignores the key but the OpenAI client requires a non-empty string.
    return get_dynamic_setting("OPENAI_FALLBACK_API_KEY", "ollama")

def get_openai_fallback_model():
    return get_dynamic_setting("OPENAI_FALLBACK_MODEL", "qwen3.5:4b")

def set_dynamic_settings(settings_dict):
    r = get_redis_client()
    if r:
        try:
            r.hset("app_settings", mapping=settings_dict)
            return True
        except Exception as e:
            print("Error saving to redis:", e)
            return False
    return False

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_TOP_N_JOBS = int(os.getenv("DISCORD_TOP_N_JOBS", "20"))
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_MODE = os.getenv("APP_MODE", "web")

# Validate critical paths (skip for celery-worker mode which only needs the env vars at runtime)
if APP_MODE != "celery-worker":
    if not get_apify_api_token() or not get_openai_api_key():
        raise ValueError("❌ Missing critical environment variables APIFY_API_TOKEN or OPENAI_API_KEY inside .env or Redis")
