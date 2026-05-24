import os
from dotenv import load_dotenv

# Don't override env vars already set by Docker
load_dotenv(override=False)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_TOP_N_JOBS = int(os.getenv("DISCORD_TOP_N_JOBS", "20"))
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_MODE = os.getenv("APP_MODE", "web")

# Validate critical paths (skip for celery-worker mode which only needs the env vars at runtime)
if APP_MODE != "celery-worker":
    if not APIFY_API_TOKEN or not OPENAI_API_KEY:
        raise ValueError("❌ Missing critical environment variables APIFY_API_TOKEN or OPENAI_API_KEY inside .env")