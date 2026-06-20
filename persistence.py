import json
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import requests
from openai import OpenAI
from config import get_openai_api_keys, get_openai_base_url, get_openai_model, DJANGO_API_URL



# Per-domain allowlist of query params that encode the job identity.
# All other params (tracking tokens, session ids, referrers) are stripped.
_DOMAIN_ID_PARAMS: dict[str, list[str]] = {
    "indeed.com": ["jk"],
    "indeed.co.jp": ["jk"],
    # Taleo ATS (e.g. company.taleo.net / oracle.taleo.net)
    "taleo.net": ["job"],
    # Jobvite ATS (hire.jobvite.com / jobs.jobvite.com)
    "jobvite.com": ["j"],
    # SAP SuccessFactors
    "successfactors.com": ["jobId"],
    "successfactors.eu": ["jobId"],
    # Workable ATS
    "workable.com": ["jid"],
    # SmartRecruiters
    "smartrecruiters.com": ["job"],
}


def normalize_url(url):
    """Normalize a job URL for deduplication.

    Strips tracking/session params and fragments; keeps only the query params
    that encode the job identity for each domain.  Most boards (LinkedIn,
    GaijinPot, CareerCross, Wantedly, Green) embed the ID in the path and
    need no query params at all.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path

    if path.endswith("/") and len(path) > 1:
        path = path[:-1]

    query_params = dict(parse_qsl(parsed.query))

    # Exact host or subdomain match only — substring matching would let
    # "notindeed.com" hit the "indeed.com" rule.
    host = netloc.split("@")[-1].split(":")[0]
    keep_keys: list[str] = []
    for domain, params in _DOMAIN_ID_PARAMS.items():
        if host == domain or host.endswith("." + domain):
            keep_keys = params
            break

    keep_params = {k: query_params[k] for k in keep_keys if k in query_params}
    new_query = urlencode(keep_params) if keep_params else ""
    return urlunparse((parsed.scheme, netloc, path, "", new_query, ""))

def detect_job_language(job_dict):
    """Detect required working language using the calibrated matching engine.

    Delegates to matching.detect_required_language so the stored label matches
    exactly what the ranker uses for its language gate \u2014 no more over-tagging
    EN-OK roles as JP just because an address contains a single kanji character.

    Returns "JP", "EN", or "non-english".
    """
    from matching import detect_required_language
    req_lang, is_hard = detect_required_language(job_dict)
    # Only label JP when Japanese is actually *required* — optional/nice-to-have
    # mentions stay EN so the stored label and dashboard filter mean "needs JP".
    if req_lang == "japanese" and is_hard:
        return "JP"
    if req_lang == "non-english" and is_hard:
        return "non-english"
    return "EN"


_RAW_LOCATION_FIELDS = (
    "location", "jobLocation", "formattedLocation", "locationName",
    "place", "city", "addressLocality", "region", "country",
)


def detect_job_location(job_dict, raw_job=None):
    """Best-effort free-text location for a job.

    Checks the formatter output and common raw Apify location fields first, then
    falls back to scanning title/description against known location aliases.
    """
    # 1. Explicit field on the formatted dict.
    loc = str(job_dict.get("location") or "").strip()
    if loc:
        return loc[:300]

    # 2. Common raw fields from the scraper payload.
    raw = raw_job if raw_job is not None else (job_dict.get("raw_data") or {})
    if isinstance(raw, dict):
        for key in _RAW_LOCATION_FIELDS:
            val = raw.get(key)
            if isinstance(val, dict):
                val = val.get("name") or val.get("city") or val.get("displayName")
            if val and isinstance(val, str) and val.strip():
                return val.strip()[:300]

    # 3. Infer a city/region from the text.
    try:
        from locations import region_for_text
        text = " ".join([
            str(job_dict.get("title") or ""),
            str(job_dict.get("description") or job_dict.get("full_description") or "")[:500],
        ])
        region, country, city = region_for_text(text)
        if city:
            return city
        if country:
            return country
    except Exception:
        pass
    return ""


class JobFormatter:
    """Processes each raw Apify job through gpt-4o-mini to format it as a Job model entry."""

    def __init__(self):
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "prompts/formatter.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.SYSTEM_PROMPT = f.read()

    @property
    def client(self):
        import random
        keys = get_openai_api_keys()
        return OpenAI(api_key=random.choice(keys) if keys else None, base_url=get_openai_base_url())

    def format_job(self, raw_job):
        """Send one raw job to the LLM and return the formatted Job model object."""
        from llm import chat_completion
        text = chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(raw_job, indent=2, default=str)},
            ],
            temperature=0.1,
            timeout=120,
            response_format={"type": "json_object"},
        )
        result = json.loads(text)
        if isinstance(result, dict):
            result["language"] = detect_job_language(result)
            result["location"] = detect_job_location(result, raw_job)
        return result

    def format_all(self, raw_jobs):
        """Process each raw job individually through gpt-4o-mini."""
        if not raw_jobs:
            return []

        formatted = []
        total = len(raw_jobs)
        print(f"\n🧪 Phase 2: Formatting {total} raw jobs via gpt-4o-mini (1 at a time)...")

        for i, raw in enumerate(raw_jobs):
            print(f"   -> [{i+1}/{total}] {raw.get('title', raw.get('standardizedTitle', '?'))[:50]}...")
            try:
                result = self.format_job(raw)

                # Ensure required fields exist
                result.setdefault("title", raw.get("title", "Unknown"))
                result.setdefault("company", raw.get("companyName", raw.get("company", "Unknown")))
                result.setdefault("url", raw.get("link", raw.get("url", raw.get("applyUrl", ""))))
                result.setdefault("source", "custom")
                result.setdefault("salary", "")
                result.setdefault("description", "")
                result.setdefault("full_description", "")
                result.setdefault("tech_stack", [])
                result.setdefault("language", "EN")
                result["language"] = detect_job_language(result)
                result["location"] = detect_job_location(result, raw)
                result.setdefault("experience_required", "")
                formatted.append(result)
            except Exception as e:
                print(f"   ❌ [{i+1}/{total}] Failed: {e}. Using raw passthrough.")
                # Minimal fallback from raw data
                fallback_job = {
                    "title": raw.get("title", raw.get("standardizedTitle", "Unknown")),
                    "company": raw.get("companyName", raw.get("company", "Unknown")),
                    "url": raw.get("link", raw.get("url", raw.get("applyUrl", ""))),
                    "source": "custom",
                    "salary": raw.get("salary", ""),
                    "description": str(raw.get("descriptionText", raw.get("description", "")))[:500],
                    "full_description": str(raw.get("descriptionText", raw.get("description", ""))),
                    "tech_stack": [],
                    "language": "EN",
                    "experience_required": "",
                }
                fallback_job["language"] = detect_job_language(fallback_job)
                fallback_job["location"] = detect_job_location(fallback_job, raw)
                formatted.append(fallback_job)

        print(f"   ✅ Formatted {len(formatted)} jobs.")
        return formatted


class DjangoPersistence:
    JOBS_URL = f"{DJANGO_API_URL}/api/jobs/bulk_create/"
    RANKINGS_URL = f"{DJANGO_API_URL}/api/rankings/bulk_create/"
    JOBS_SEARCH_URL = f"{DJANGO_API_URL}/api/jobs/"

    def fetch_unformatted_jobs(self):
        """Fetch today's jobs that haven't been formatted yet."""
        from datetime import date
        today = date.today().isoformat()
        all_jobs = []
        url = f"{self.JOBS_SEARCH_URL}?is_formatted=false&from={today}&page_size=100"
        while url:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            all_jobs.extend(data.get("results", []))
            url = data.get("next")
        return all_jobs

    def update_job(self, job_id, formatted_data):
        """Update an existing job record with formatted data."""
        url = f"{DJANGO_API_URL}/api/jobs/{job_id}/"
        response = requests.patch(url, json=formatted_data, timeout=30)
        response.raise_for_status()
        return response.json()

    def save_jobs(self, jobs):
        """POST formatted jobs to the Django bulk_create endpoint."""
        response = requests.post(self.JOBS_URL, json=jobs, timeout=30)
        response.raise_for_status()
        result = response.json()
        errors = result.get("errors", [])
        print(f"   -> Jobs: {result.get('created', 0)} created, "
              f"{result.get('updated', 0)} updated, "
              f"{len(errors)} errors")
        for err in errors:
            print(f"      ⚠️ {err}")
        return result

    def fetch_jobs_today(self):
        """Fetch jobs updated today from the Django API."""
        from datetime import date
        today = date.today().isoformat()
        all_jobs = []
        url = f"{self.JOBS_SEARCH_URL}?page_size=100&from={today}"
        while url:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            all_jobs.extend(data.get("results", []))
            url = data.get("next")
        print(f"   -> Fetched {len(all_jobs)} jobs updated today from DB.")
        return all_jobs


    def _fetch_job_by_url(self, url):
        """Fetch the full job object from the API by URL."""
        response = requests.get(
            self.JOBS_SEARCH_URL,
            params={"url": url, "page_size": 1},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        return results[0] if results else None



    def persist_jobs(self, jobs):
        """POST formatted jobs to the backend."""
        print("\n🗄️  Phase 3: Saving formatted jobs to Django backend...")
        try:
            self.save_jobs(jobs)
            print("   ✅ Jobs persisted.")
        except requests.ConnectionError:
            print("   ⚠️ Could not connect to Django API at " + DJANGO_API_URL)
            print("   ⚠️ Skipping. Start backend with: docker compose up")
        except requests.RequestException as e:
            print(f"   ⚠️ Job persistence failed: {e}")
