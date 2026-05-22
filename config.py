import os
from dotenv import load_dotenv

load_dotenv()

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_TOP_N_JOBS = int(os.getenv("DISCORD_TOP_N_JOBS", "20"))

# Validate critical paths
if not APIFY_API_TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ Missing critical environment variables APIFY_API_TOKEN or OPENAI_API_KEY inside .env")