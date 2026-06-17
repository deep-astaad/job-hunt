import json
import re
from urllib.parse import urlparse, urlunparse
import requests
from openai import OpenAI
from config import get_openai_api_keys, get_openai_base_url, get_openai_model, DJANGO_API_URL


def normalize_url(url):
    """Normalize URL for comparison: strip query params and fragments."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def detect_job_language(job_dict):
    """Detect and normalize language choice based on content and language field."""
    lang = str(job_dict.get("language", "")).strip().upper()
    if lang in ("JP", "JAPANESE"):
        lang = "JP"
    elif lang in ("EN", "ENGLISH"):
        lang = "EN"
    elif lang in ("NON-ENGLISH", "NON_ENGLISH"):
        lang = "non-english"
    else:
        lang = "EN"

    # Check description, title, etc. for explicit Japanese requirements
    desc = (job_dict.get("full_description") or job_dict.get("description") or "").lower()
    title = (job_dict.get("title") or "").lower()

    if not desc and "raw_data" in job_dict:
        raw_data = job_dict["raw_data"] or {}
        desc = str(raw_data.get("descriptionText", raw_data.get("description", ""))).lower()

    # Define common phrases suggesting Japanese is required
    jp_indicators = [
        r"business[- ]level japanese",
        r"japanese[:\s]+business",
        r"fluent japanese",
        r"japanese[:\s]+fluent",
        r"native japanese",
        r"japanese[:\s]+native",
        r"japanese[- ]level[\s:]+fluent",
        r"jlpt[\s]*n[1-3]",
        r"japanese required",
        r"japanese is required",
        r"all text in japanese",
        r"japanese language proficiency",
        r"language: japanese and english",
        r"english and japanese required",
    ]

    for pattern in jp_indicators:
        if re.search(pattern, desc) or re.search(pattern, title):
            return "JP"

    # Check if text contains Japanese characters (Hiragana, Katakana, or common Kanji)
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]", desc) or re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]", title):
        return "JP"

    return lang


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
        ).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        result = json.loads(text.strip())
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

    def _parse_ranking_markdown(self, markdown_text, profile_id, profile_title):
        lines = [l.strip() for l in markdown_text.strip().split("\n") if l.strip().startswith("|")]
        if len(lines) < 3:
            return []
        rankings = []
        for line in lines[2:]:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) < 8:
                continue
            rank_str, tier, title_company, salary, exp, lang, summary, url_cell = cells
            url_match = re.search(r"\((https?://[^\)]+)\)", url_cell)
            url = url_match.group(1) if url_match else None
            try:
                rank = int(rank_str.strip())
            except ValueError:
                continue
            rankings.append({
                "url": url,
                "profile_id": profile_id,
                "profile_title": profile_title,
                "match_tier": tier.strip().upper(),
                "rank": rank,
                "jd_summary": summary.strip(),
            })
        return rankings

    def _post_rankings(self, rankings_data):
        enriched_rankings = []
        for r in rankings_data:
            if not r.get("url"):
                continue
            try:
                job_id = self._fetch_job_id_by_url(r["url"])
            except requests.RequestException:
                print(f"   ⚠️ Could not reach API for URL: {r['url']}")
                continue
            if job_id:
                enriched_rankings.append({
                    "job_id": job_id,
                    "profile_id": r["profile_id"],
                    "profile_title": r.get("profile_title", ""),
                    "match_tier": r["match_tier"],
                    "rank": r["rank"],
                    "jd_summary": r.get("jd_summary", ""),
                })
            else:
                print(f"   ⚠️ Could not find job for URL: {r['url']}")

        if not enriched_rankings:
            print("   ⚠️ No rankings to persist (no matching jobs found).")
            return

        response = requests.post(self.RANKINGS_URL, json=enriched_rankings, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"   -> Rankings: {result.get('created', 0)} created, "
              f"{result.get('updated', 0)} updated")
        return result

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

    def _fetch_job_id_by_url(self, url):
        job = self._fetch_job_by_url(url)
        return job["id"] if job else None

    def save_rankings(self, markdown_result, profile_id, profile_title, db_jobs):
        """Parse ranking markdown and POST to backend."""
        print("\n🗄️  Phase 4: Persisting rankings to Django backend...")
        try:
            # Build ID lookup from the jobs we already fetched (these are the jobs we ranked)
            url_to_id = {normalize_url(j["url"]): j["id"] for j in db_jobs if j.get("url") and j.get("id")}
            rankings = self._parse_ranking_markdown(markdown_result, profile_id, profile_title)
            if not rankings:
                print("   ⚠️ No rankings parsed from markdown table.")
                return

            enriched_rankings = []
            for r in rankings:
                url = r.get("url")
                job_id = url_to_id.get(normalize_url(url)) if url else None
                if job_id:
                    enriched_rankings.append({
                        "job_id": job_id,
                        "profile_id": r["profile_id"],
                        "profile_title": r.get("profile_title", ""),
                        "match_tier": r["match_tier"],
                        "rank": r["rank"],
                        "jd_summary": r.get("jd_summary", ""),
                    })

            if not enriched_rankings:
                print("   ⚠️ No rankings to persist (no matching jobs found).")
                return

            response = requests.post(self.RANKINGS_URL, json=enriched_rankings, timeout=30)
            response.raise_for_status()
            result = response.json()
            print(f"   -> Rankings: {result.get('created', 0)} created, "
                  f"{result.get('updated', 0)} updated")
            print("   ✅ Rankings persisted.")
        except requests.ConnectionError:
            print("   ⚠️ Could not connect to Django API at " + DJANGO_API_URL)
        except requests.RequestException as e:
            print(f"   ⚠️ Ranking persistence failed: {e}")

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
