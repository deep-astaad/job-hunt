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

# ---------------------------------------------------------------------------
# Required-language detection (formerly matching.py)
# ---------------------------------------------------------------------------
# Issue #125 deleted the deterministic matching/ranking engine (matching.py) \u2014
# the LLM ranks every job now, with no deterministic tier assignment or hard
# gates. This text-driven language detector is the one piece of that module
# that survives: it is pure data extraction (never assigns a tier) and
# `detect_job_language` below uses it during *formatting* to populate
# `job.language`. Kept here, inline, since this was the only remaining caller
# and the surviving surface is small enough not to warrant its own module.

# Languages a job might require, with the keywords that signal a *hard* requirement.
_NON_ENGLISH_LANG_KEYWORDS = {
    "japanese": ["japanese", "\u65e5\u672c\u8a9e", "jlpt", "nihongo"],
    "german": ["german", "deutsch"],
    "french": ["french", "fran\u00e7ais", "francais"],
    "mandarin": ["mandarin", "chinese", "\u4e2d\u6587", "\u666e\u901a\u8bdd"],
    "korean": ["korean", "\ud55c\uad6d\uc5b4"],
    "spanish": ["spanish", "espa\u00f1ol", "espanol"],
    "dutch": ["dutch", "nederlands"],
}
# Phrases that turn a "mention" into a hard requirement.
_REQUIRED_PHRASES = [
    "required", "mandatory", "must", "necessary", "fluent", "native",
    "business level", "business-level", "proficiency", "proficient",
    "n1", "n2", "n3", "jlpt",
]
# Phrases that explicitly soften it (a plus, not a gate).
_OPTIONAL_PHRASES = [
    "is a plus", "a plus", "preferred", "nice to have", "advantage",
    "helpful", "not required", "no japanese", "english ok", "english only",
    "welcome", "beneficial", "bonus",
]

# --- Japanese requirement detection (text-driven) --------------------------
# The stored `language` label tags *any* job with CJK characters as "JP" (company
# boilerplate, benefits, \u00a5 salary), which over-gated ~86% of the corpus as
# "requires Japanese" \u2014 burying English-OK Tokyo roles. We instead infer the
# Japanese demand from the text itself, precision-tuned against the live DB.
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def cjk_density(text):
    """Fraction of characters that are Japanese kana / CJK ideographs (0..1).

    A description written largely in Japanese implies the working language is
    Japanese even when it states no explicit requirement.
    """
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


# Explicit hard Japanese requirement: \u65e5\u672c\u8a9e\u5fc5\u9808 / JLPT N1-N2 / "business-level
# (fluent/native/...) Japanese" / "Japanese ... required/mandatory".
_JP_HARD_RE = re.compile(
    r"\u65e5\u672c\u8a9e(?:\u80fd\u529b)?(?:\u304c|\u306f|\u3092|\u30fb|\s|\uff1a|:)*(?:\u5fc5\u9808|\u5fc5\u8981|\u30d3\u30b8\u30cd\u30b9|\u30cd\u30a4\u30c6\u30a3\u30d6|\u582a\u80fd|\u6d41\u66a2)"
    r"|\u65e5\u672c\u8a9e\u5fc5\u9808|\u30cd\u30a4\u30c6\u30a3\u30d6\u30ec\u30d9\u30eb|\u6bcd\u8a9e\u30ec\u30d9\u30eb"
    r"|jlpt\s*[-\u2013 ]?\s*n?\s*[12]\b"
    r"|\bn\s*[12]\b\s*(?:\u4ee5\u4e0a|\u30ec\u30d9\u30eb|level|\u76f8\u5f53|required)"
    r"|(?:business[- ]?level|fluent|native|conversational|proficien\w+)\s+japanese"
    r"|japanese[^.\n\u3002!?]{0,30}(?:required|mandatory|fluent|native|business[- ]?level|proficien|\u5fc5\u9808)",
    re.I,
)
# Soft signal: Japanese is "a plus / preferred / welcome", or a low JLPT level.
_JP_SOFT_RE = re.compile(
    r"japanese[^.\n\u3002!?]{0,25}(?:plus|preferred|nice to have|welcome|advantage|beneficial|bonus|good to have|is an asset)"
    r"|\u65e5\u672c\u8a9e[^\u3002\n]{0,8}(?:\u5c1a\u53ef|\u6b53\u8fce|\u3042\u308c\u3070|\u3067\u304d\u308c\u3070)"
    r"|jlpt\s*[-\u2013 ]?\s*n?\s*[345]\b|\bn\s*[345]\b\s*(?:\u4ee5\u4e0a|\u30ec\u30d9\u30eb|level)",
    re.I,
)
# Explicit English-OK escape hatch (wins over the hard pattern above).
_JP_ENGLISH_OK_RE = re.compile(
    r"no japanese(?:\s+language)?(?:\s+skills?)?(?:\s+(?:is|are))?\s+(?:required|necessary|needed)"
    r"|japanese[^.\n\u3002!?]{0,30}(?:not required|not necessary|not needed|not mandatory|: ?not|\uff1a?\u306a\u3057|n/a|optional)"
    r"|japanese level\s*[:\uff1a]?\s*(?:not required|n/a|none|optional|free|\u306a\u3057)"
    r"|japanese\s+or\s+english|english\s+or\s+japanese"
    r"|english[- ]?only|english\s+ok|no japanese ability|without japanese|no japanese required",
    re.I,
)
# Bare JLPT shorthand "N1"/"N2" (counts only with Japanese/bilingual context).
_JP_BARE_LEVEL_RE = re.compile(r"(?<![a-z0-9])n\s*[12](?![0-9])", re.I)

_JP_DENSITY_HARD = 0.55  # JD overwhelmingly in Japanese -> working language is JP
_JP_DENSITY_SOFT = 0.20


def japanese_requirement(text, lang_field=""):
    """Classify a job's Japanese-language demand as 'hard' | 'soft' | 'none'."""
    low = text.lower()
    lang_field = (lang_field or "").strip().upper()
    if _JP_ENGLISH_OK_RE.search(low):
        return "none"
    if _JP_HARD_RE.search(text):
        return "hard"
    has_ctx = (
        bool(_CJK_RE.search(text))
        or "japanese" in low or "nihongo" in low or "jlpt" in low or "bilingual" in low
    )
    if _JP_BARE_LEVEL_RE.search(text) and (has_ctx or lang_field == "JP"):
        return "hard"
    d = cjk_density(text)
    if d >= _JP_DENSITY_HARD:
        return "hard"
    if _JP_SOFT_RE.search(text):
        return "soft"
    if d >= _JP_DENSITY_SOFT and has_ctx:
        return "soft"
    # Labelled JP with some context but no explicit requirement -> soft, not hard.
    if lang_field == "JP" and has_ctx:
        return "soft"
    return "none"


def detect_required_language(job):
    """Return (language, is_hard_requirement) for the strongest non-English
    language a job appears to *require*. (None, False) if none / English only."""
    lang_field = str(job.get("language") or "").strip().lower()
    text = " ".join([
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(job.get("full_description") or ""),
    ])
    low = text.lower()

    # Japanese: robust, text-driven (the JP label alone is not a requirement).
    jp = japanese_requirement(text, lang_field)
    if jp == "hard":
        return "japanese", True
    if jp == "soft":
        return "japanese", False

    if lang_field in ("non-english", "non_english"):
        # Unknown which language, treat as a hard non-English gate.
        return "non-english", True

    # Other non-English languages: explicit-phrase driven only.
    for canon, keywords in _NON_ENGLISH_LANG_KEYWORDS.items():
        if canon == "japanese":
            continue
        if any(kw in low for kw in keywords):
            return canon, _looks_required(canon, low)
    return None, False


def _looks_required(canon, text, default_required=False):
    # Find the sentence/window around the language keyword and weigh phrases.
    keywords = _NON_ENGLISH_LANG_KEYWORDS.get(canon, [canon])
    for kw in keywords:
        idx = text.find(kw)
        if idx == -1:
            continue
        window = text[max(0, idx - 80): idx + 80]
        if any(p in window for p in _OPTIONAL_PHRASES):
            return False
        if any(p in window for p in _REQUIRED_PHRASES):
            return True
    return default_required


def detect_job_language(job_dict):
    """Detect required working language using the text-driven detector above.

    Returns "JP", "EN", or "non-english".
    """
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
