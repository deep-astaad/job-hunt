"""Pure-Python parsers for deriving structured fields from free-text job data.

Kept free of Django imports so both models.py (at save time) and web_views.py
(for analytics) can use them without a circular import.
"""
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


# Per-domain allowlist of query params that encode the job identity.
# Keep this in sync with persistence.py:_DOMAIN_ID_PARAMS.
_DOMAIN_ID_PARAMS = {
    "indeed.com": ["jk"],
    "indeed.co.jp": ["jk"],
    "taleo.net": ["job"],
    "jobvite.com": ["j"],
    "successfactors.com": ["jobId"],
    "successfactors.eu": ["jobId"],
    "workable.com": ["jid"],
    "smartrecruiters.com": ["job"],
}


def normalize_url(url):
    """Normalize a job URL for deduplication.

    Strips tracking/session params and fragments; keeps only the query params
    that encode the job identity for each domain.  Most boards embed the ID in
    the path and need no query params at all.
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
    keep_keys: list = []
    for domain, params in _DOMAIN_ID_PARAMS.items():
        if host == domain or host.endswith("." + domain):
            keep_keys = params
            break

    keep_params = {k: query_params[k] for k in keep_keys if k in query_params}
    new_query = urlencode(keep_params) if keep_params else ""
    return urlunparse((parsed.scheme, netloc, path, "", new_query, ""))


def normalize_skill(value):
    """Normalize a skill/tech name for case-insensitive comparison."""
    return str(value).strip().lower()


def parse_salary_to_yen(text):
    """Best-effort parse of a free-text salary into an estimated annual yen figure.

    Handles ranges (averaged), Japanese 万 units, k/M suffixes, and rough USD->JPY.
    Returns None when nothing usable is found.
    """
    if not text:
        return None
    s = str(text).lower().replace(",", "").replace("，", "")
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return None
    vals = [float(n) for n in nums]
    if "万" in s:
        vals = [v * 10000 for v in vals]
    elif "m" in s or "million" in s:
        vals = [v * 1_000_000 for v in vals]
    elif "k" in s:
        vals = [v * 1000 for v in vals]
    if "$" in s or "usd" in s:
        vals = [v * 150 for v in vals]  # rough USD->JPY for comparability
    rep = sum(vals) / len(vals)
    # Discard implausible figures: anything under ~¥1k (hourly/garbage) or over
    # ¥1B (parsing artifacts, equity pools, currency confusion). The upper bound
    # also keeps the value within MySQL INT UNSIGNED range (salary_yen column).
    if rep < 1000 or rep > 1_000_000_000:
        return None
    return int(rep)


def required_jlpt_level(text):
    """Infer the JLPT level a job demands as an int (1=N1 hardest .. 5=N5 easiest).

    Returns None when no Japanese requirement is detectable.
    """
    if not text:
        return None
    s = str(text).lower()
    explicit = re.findall(r"n\s*([1-5])", s)
    if explicit:
        return min(int(x) for x in explicit)  # hardest level mentioned
    if any(k in s for k in ["native", "母語", "ネイティブ"]):
        return 1
    if any(k in s for k in ["business", "fluent", "ビジネス", "流暢"]):
        return 2
    if "japanese" in s or "日本語" in s:
        return 3  # generic conversational assumption
    return None


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
# Compact keyword -> (region, country, city) map mirroring locations.json so
# models.save() can derive structured location fields without depending on the
# repo-root locations module being importable. Keep in sync with locations.json.
_REGION_KEYWORDS = [
    # (keywords, region, country, city)
    (["tokyo", "東京", "yokohama", "kanto"], "japan", "JP", "Tokyo"),
    (["osaka", "kyoto", "japan", "日本"], "japan", "JP", ""),
    (["bangalore", "bengaluru", "hyderabad", "pune", "gurgaon", "noida",
      "mumbai", "delhi", "india"], "india", "IN", ""),
    (["berlin", "munich", "hamburg", "germany", "deutschland"], "europe", "DE", ""),
    (["amsterdam", "rotterdam", "utrecht", "netherlands", "holland"], "europe", "NL", ""),
    (["london", "manchester", "united kingdom", "england", " uk "], "europe", "GB", ""),
    (["paris", "france"], "europe", "FR", ""),
    (["dublin", "ireland"], "europe", "IE", ""),
    (["singapore"], "apac", "SG", "Singapore"),
    (["san francisco", "new york", "seattle", "austin", "united states",
      " usa", "u.s.", " us "], "north_america", "US", ""),
    (["toronto", "vancouver", "canada"], "north_america", "CA", ""),
]

_REMOTE_RE = re.compile(
    r"\b(remote|work from home|wfh|fully remote|work from anywhere|distributed team)\b",
    re.I,
)


def parse_location_region(text):
    """Best-effort (region, country, city) from free-text. Empty strings if unknown."""
    if not text:
        return "", "", ""
    s = f" {str(text).lower()} "
    for keywords, region, country, city in _REGION_KEYWORDS:
        if any(kw in s for kw in keywords):
            return region, country, city
    return "", "", ""


def detect_remote_text(text):
    """True if the text indicates a remote-friendly role."""
    if not text:
        return False
    return bool(_REMOTE_RE.search(str(text)))
