"""Deterministic job<->profile matching engine.

This module is intentionally dependency-free (pure Python, no Django/openai/redis)
so it can run inside Celery tasks, the Django request cycle, and unit tests alike.

The LLM ranker (`prompts/ranker.txt`) is good at reading prose but it only ever
sees a slice of the job and it is non-deterministic and (on cheap/local models)
unreliable. This module computes a *deterministic*, explainable match score from
the structured fields we already store, then `blend_with_llm()` fuses the two into
a final tier + numeric score. The deterministic layer is what makes ranking
robust even when the LLM is mocked, rate-limited, or a tiny local Ollama model.

Public API:
    compute_match(profile, job, location_cfgs=None) -> MatchResult-as-dict
    blend_with_llm(deterministic, llm_tier) -> dict(final tier/score)
    score_to_tier(score) / tier_to_score(tier)
    canonical_skill(name)
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------
TIER_ORDER = ["S", "A", "B", "C", "F"]
# Representative numeric score for a tier (used to fold LLM output into the blend).
TIER_SCORE = {"S": 92, "A": 74, "B": 56, "C": 38, "F": 8}

# Score thresholds -> tier. Tunable single source of truth.
_TIER_THRESHOLDS = [(80, "S"), (64, "A"), (48, "B"), (30, "C")]


def score_to_tier(score):
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "F"


def tier_to_score(tier):
    return TIER_SCORE.get((tier or "").strip().upper(), 38)


# ---------------------------------------------------------------------------
# Skill canonicalization
# ---------------------------------------------------------------------------
# Map noisy aliases to a single canonical token so "JS"/"Javascript"/"ECMAScript"
# all compare equal. Keys are lowercased; lookups normalize first.
_SKILL_ALIASES = {
    "js": "javascript", "ecmascript": "javascript", "node": "node.js",
    "nodejs": "node.js", "node js": "node.js",
    "ts": "typescript",
    "py": "python", "python3": "python",
    "golang": "go",
    "postgres": "postgresql", "psql": "postgresql",
    "mysql8": "mysql",
    "k8s": "kubernetes",
    "gcp": "google cloud", "google cloud platform": "google cloud",
    "amazon web services": "aws",
    "ms azure": "azure", "azure cloud": "azure",
    "reactjs": "react", "react.js": "react",
    "vuejs": "vue", "vue.js": "vue",
    "nextjs": "next.js", "next": "next.js",
    "tf": "terraform",
    "cicd": "ci/cd", "ci cd": "ci/cd",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "llms": "llm", "large language models": "llm", "large language model": "llm",
    "rest api": "rest", "restful": "rest", "apis": "api",
    "dl": "deep learning",
    "rdbms": "sql", "relational database": "sql",
    "nosql databases": "nosql",
    "gha": "github actions",
    "pg": "postgresql",
    "c sharp": "c#", "csharp": "c#",
    "cpp": "c++", "c plus plus": "c++",
    "fast api": "fastapi",
    "dotnet": ".net", "asp.net": ".net",
}

# Canonical vocabulary scanned for inside free-text job descriptions. Multi-word
# entries are matched as phrases; single tokens as word boundaries.
_SKILL_VOCAB = {
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin", "scala",
    "c++", "c#", "c", "ruby", "php", "swift", "elixir",
    "django", "flask", "fastapi", "celery", "rails", "spring", "express",
    "react", "vue", "angular", "svelte", "next.js", "node.js",
    "postgresql", "mysql", "sql", "nosql", "mongodb", "redis", "elasticsearch",
    "cassandra", "dynamodb", "kafka", "rabbitmq", "sqs",
    "aws", "azure", "google cloud", "docker", "kubernetes", "terraform",
    "ansible", "nginx", "gunicorn", "linux", "bash",
    "ci/cd", "github actions", "gitlab", "jenkins", "argocd",
    "graphql", "rest", "grpc", "api",
    "machine learning", "deep learning", "artificial intelligence", "llm", "rag",
    "pytorch", "tensorflow", "pandas", "numpy", "spark", "airflow", "dbt",
    "microservices", "distributed systems", "system design", "data pipelines",
    "web scraping", "etl", "observability", "prometheus", "grafana",
    ".net",
}

# Tokens that are also ordinary English words ("go", "on the go"; "c"; "rust";
# "ruby" as a name; "spark"/"swift" generic). Word-boundary scanning these in
# free text produces false skills (a hotel "Dining Server" matched "go"). We
# therefore only honour them from the structured `tech_stack`, not the text scan.
_AMBIGUOUS_TEXT_TOKENS = {"go", "c", "rust", "ruby", "swift", "spark", "scala", "express", "rest"}
_TEXT_SCAN_VOCAB = _SKILL_VOCAB - _AMBIGUOUS_TEXT_TOKENS


def canonical_skill(name):
    """Normalize a single skill/tech string to its canonical token."""
    s = re.sub(r"\s+", " ", str(name or "").strip().lower())
    s = s.strip(" .,/|()-")
    return _SKILL_ALIASES.get(s, s)


def _canon_set(skills):
    out = set()
    for s in skills or []:
        c = canonical_skill(s)
        if c:
            out.add(c)
    return out


def extract_job_skills(job):
    """Best-effort set of canonical skills a job involves.

    Combines the structured `tech_stack` with a vocabulary scan of the title +
    description, so jobs whose tech_stack the formatter missed still get signal.
    """
    skills = _canon_set(job.get("tech_stack") or [])

    text_parts = [
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(job.get("full_description") or ""),
    ]
    text = " ".join(text_parts).lower()
    if text.strip():
        for vocab in _TEXT_SCAN_VOCAB:
            if " " in vocab or any(ch in vocab for ch in "+#./"):
                # Phrase / symbol-bearing token: substring match is safe enough.
                if vocab in text:
                    skills.add(vocab)
            else:
                if re.search(r"\b" + re.escape(vocab) + r"\b", text):
                    skills.add(vocab)
    return skills


# ---------------------------------------------------------------------------
# Experience / seniority
# ---------------------------------------------------------------------------
_SENIOR_TITLE_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|head|director|architect|"
    r"engineering manager|vp|chief|distinguished)\b",
    re.I,
)
_JUNIOR_TITLE_RE = re.compile(
    r"\b(junior|jr\.?|entry[- ]level|new ?grad|graduate|associate|intern|trainee|apprentice)\b",
    re.I,
)
_INTERN_RE = re.compile(r"\b(intern|internship|trainee|apprentice|placement)\b", re.I)


def parse_required_years(text):
    """Extract the minimum years of experience a job demands, or None."""
    if not text:
        return None
    s = str(text).lower()
    # "3+ years", "3-5 years", "minimum 3 years", "at least 3 yrs", "0.5 years".
    # Decimals must be captured or "0.5 years" wrongly parses as 5.
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|-|to|–)?\s*(?:\d+(?:\.\d+)?)?\s*\+?\s*(?:years?|yrs?)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def parse_profile_years(profile):
    exp = profile.get("experience_years")
    if isinstance(exp, (int, float)):
        return float(exp)
    m = re.search(r"(\d+(?:\.\d+)?)", str(profile.get("experience", "")))
    return float(m.group(1)) if m else 0.0


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
# Languages a job might require, with the keywords that signal a *hard* requirement.
_NON_ENGLISH_LANG_KEYWORDS = {
    "japanese": ["japanese", "日本語", "jlpt", "nihongo"],
    "german": ["german", "deutsch"],
    "french": ["french", "français", "francais"],
    "mandarin": ["mandarin", "chinese", "中文", "普通话"],
    "korean": ["korean", "한국어"],
    "spanish": ["spanish", "español", "espanol"],
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


def candidate_languages(profile):
    """Set of canonical languages the candidate can work in (always includes english)."""
    langs = {"english"}
    raw = profile.get("languages")
    if isinstance(raw, list):
        for l in raw:
            langs.add(str(l).strip().lower())
    text = str(profile.get("language_requirements", "")).lower()
    for canon in _NON_ENGLISH_LANG_KEYWORDS:
        if canon in text and "no mandatory" not in text:
            # Only add if it reads like an ability, not a "no X required" note.
            if f"no {canon}" not in text and "not required" not in text:
                langs.add(canon)
    return langs


# --- Japanese requirement detection (text-driven) --------------------------
# The stored `language` label tags *any* job with CJK characters as "JP" (company
# boilerplate, benefits, ¥ salary), which over-gated ~86% of the corpus as
# "requires Japanese" — burying English-OK Tokyo roles. We instead infer the
# Japanese demand from the text itself, precision-tuned against the live DB.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def cjk_density(text):
    """Fraction of characters that are Japanese kana / CJK ideographs (0..1).

    A description written largely in Japanese implies the working language is
    Japanese even when it states no explicit requirement.
    """
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


# Explicit hard Japanese requirement: 日本語必須 / JLPT N1-N2 / "business-level
# (fluent/native/...) Japanese" / "Japanese ... required/mandatory".
_JP_HARD_RE = re.compile(
    r"日本語(?:能力)?(?:が|は|を|・|\s|：|:)*(?:必須|必要|ビジネス|ネイティブ|堪能|流暢)"
    r"|日本語必須|ネイティブレベル|母語レベル"
    r"|jlpt\s*[-– ]?\s*n?\s*[12]\b"
    r"|\bn\s*[12]\b\s*(?:以上|レベル|level|相当|required)"
    r"|(?:business[- ]?level|fluent|native|conversational|proficien\w+)\s+japanese"
    r"|japanese[^.\n。!?]{0,30}(?:required|mandatory|fluent|native|business[- ]?level|proficien|必須)",
    re.I,
)
# Soft signal: Japanese is "a plus / preferred / welcome", or a low JLPT level.
_JP_SOFT_RE = re.compile(
    r"japanese[^.\n。!?]{0,25}(?:plus|preferred|nice to have|welcome|advantage|beneficial|bonus|good to have|is an asset)"
    r"|日本語[^。\n]{0,8}(?:尚可|歓迎|あれば|できれば)"
    r"|jlpt\s*[-– ]?\s*n?\s*[345]\b|\bn\s*[345]\b\s*(?:以上|レベル|level)",
    re.I,
)
# Explicit English-OK escape hatch (wins over the hard pattern above).
_JP_ENGLISH_OK_RE = re.compile(
    r"no japanese(?:\s+language)?(?:\s+skills?)?(?:\s+(?:is|are))?\s+(?:required|necessary|needed)"
    r"|japanese[^.\n。!?]{0,30}(?:not required|not necessary|not needed|not mandatory|: ?not|：?なし|n/a|optional)"
    r"|japanese level\s*[:：]?\s*(?:not required|n/a|none|optional|free|なし)"
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


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|fully remote|anywhere|distributed team)\b", re.I)


def detect_remote(job):
    text = " ".join([
        str(job.get("location") or ""),
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(job.get("full_description") or ""),
    ])
    return bool(_REMOTE_RE.search(text))


def job_location_text(job):
    return " ".join([
        str(job.get("location") or ""),
        str(job.get("country") or ""),
        str(job.get("region") or ""),
    ]).strip().lower()


def location_match(job, location_cfgs):
    """Score how well a job's location matches the candidate's target locations.

    Returns (score 0..1, matched_location_id_or_None, is_remote).
    location_cfgs: list of dicts each with id/aliases/country/region/city.
    """
    is_remote = detect_remote(job)
    if not location_cfgs:
        return 1.0, None, is_remote

    # Any target that is itself a remote bucket means remote jobs always match.
    if is_remote and any(c.get("remote") for c in location_cfgs):
        remote_cfg = next(c for c in location_cfgs if c.get("remote"))
        return 1.0, remote_cfg.get("id"), True

    loc_text = job_location_text(job)
    blob = " ".join([
        loc_text,
        str(job.get("title") or "").lower(),
        str(job.get("description") or "").lower()[:400],
    ])

    if not loc_text and not is_remote:
        # Unknown location → could be anywhere; modest penalty without hard-failing.
        return 0.35, None, is_remote

    for cfg in location_cfgs:
        aliases = [a.lower() for a in cfg.get("aliases", [])]
        for token in (
            [cfg.get("city", ""), cfg.get("country", ""), cfg.get("region", "")] + aliases
        ):
            token = str(token or "").strip().lower()
            if token and token in blob:
                return 1.0, cfg.get("id"), is_remote

    # Remote job but no remote-target configured: partial credit (often still ok).
    if is_remote:
        return 0.75, None, True

    # Location known and matched nothing in the target set.
    return 0.15, None, is_remote


# ---------------------------------------------------------------------------
# Title affinity
# ---------------------------------------------------------------------------
# Keywords are matched against the job TITLE. Tokens must be specific enough that
# they don't fire on non-engineering titles — bare "server" (hotel "Dining
# Server"), "platform", "api", "go" were over-broad and are now qualified.
_ROLE_FAMILIES = {
    "backend": ["backend", "back-end", "back end", "server-side", "server engineer",
                "api engineer", "api developer", "platform engineer", "python",
                "django", "node.js", "nodejs", "golang", "java developer",
                "java engineer", "ruby on rails", "php developer",
                "software engineer", "software developer", "full stack", "fullstack"],
    "frontend": ["frontend", "front-end", "front end", "react", "vue", "angular",
                 "ui engineer", "web developer", "web engineer"],
    "devops": ["devops", "dev ops", "sre", "site reliability", "infrastructure",
               "cloud engineer", "cloud architect", "platform engineer",
               "kubernetes", "software systems engineer"],
    "data": ["data engineer", "data scientist", "machine learning", "ml engineer",
             "ai engineer", "mlops", "analytics engineer"],
    "fullstack": ["full stack", "fullstack", "full-stack", "software engineer",
                  "software developer"],
    "mobile": ["ios", "android", "mobile", "flutter", "react native"],
}


def _families_for(text):
    text = (text or "").lower()
    fams = set()
    for fam, kws in _ROLE_FAMILIES.items():
        if any(kw in text for kw in kws):
            fams.add(fam)
    return fams


def title_affinity(profile, job):
    p_fams = _families_for(profile.get("title", "")) | _families_for(
        " ".join(profile.get("core_skills", []))
    )
    j_fams = _families_for(job.get("title", ""))
    if not j_fams:
        # No recognisable engineering/tech family in title → likely non-tech role; be skeptical.
        return 0.3
    if p_fams & j_fams:
        return 1.0
    # Adjacent families (backend<->devops, backend<->fullstack) get partial credit.
    adjacency = {
        ("backend", "devops"), ("backend", "fullstack"), ("backend", "data"),
        ("devops", "data"), ("fullstack", "frontend"),
    }
    for pf in p_fams:
        for jf in j_fams:
            if (pf, jf) in adjacency or (jf, pf) in adjacency:
                return 0.6
    return 0.2


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------
def salary_score(job, profile):
    yen = job.get("salary_yen")
    min_yen = profile.get("min_salary_yen")
    if not yen:
        return 0.5  # unknown -> neutral
    if not min_yen:
        # No floor set: reward higher pay gently (¥4M baseline .. ¥12M great).
        return max(0.4, min(1.0, yen / 12_000_000))
    if yen >= min_yen:
        return 1.0
    return max(0.0, yen / min_yen)


# ---------------------------------------------------------------------------
# Skill overlap
# ---------------------------------------------------------------------------
def skill_overlap(profile, job):
    p_skills = _canon_set(profile.get("core_skills", []))
    j_skills = extract_job_skills(job)
    if not j_skills:
        # No extractable tech at all → almost always non-tech or an unparseable
        # (e.g. Japanese-only) JD. Strong skepticism; the relevance cap in
        # compute_match keeps these out of the top tiers.
        return 0.1, [], []
    matched = sorted(p_skills & j_skills)
    missing = sorted(j_skills - p_skills)
    if not p_skills:
        return 0.3, matched, missing
    # Coverage relative to the smaller of (profile breadth capped at 8, job needs).
    denom = max(3, min(8, len(j_skills)))
    coverage = len(matched) / denom
    return min(1.0, coverage), matched, missing


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------
_WEIGHTS = {
    "skill": 0.34,
    "title": 0.16,
    "experience": 0.20,
    "language": 0.15,
    "location": 0.15,
}


def compute_match(profile, job, location_cfgs=None):
    """Score one job against one profile deterministically.

    Returns a dict:
        score:        0..100 blended-ready deterministic score
        tier:         deterministic tier from score (after hard rules)
        hard_fail:    bool
        hard_fail_reason: str|None
        signals:      per-dimension diagnostics (0..1) + matched/missing skills
    """
    signals = {}

    sk, matched, missing = skill_overlap(profile, job)
    signals["skill"] = round(sk, 3)

    ttl = title_affinity(profile, job)
    signals["title"] = round(ttl, 3)

    # Experience
    profile_years = parse_profile_years(profile)
    req_years = parse_required_years(job.get("experience_required"))
    title = str(job.get("title") or "")
    is_junior_title = bool(_JUNIOR_TITLE_RE.search(title))
    # Junior/graduate marker overrides senior keyword (e.g. "Solutions Architect Graduate").
    is_senior = bool(_SENIOR_TITLE_RE.search(title)) and not is_junior_title
    is_intern = bool(_INTERN_RE.search(title)) or "intern" in str(job.get("experience_required") or "").lower()
    if req_years is None:
        exp = 0.7 if not is_senior else 0.3
    else:
        gap = req_years - profile_years
        if gap <= 0:
            exp = 1.0
        elif gap <= 1:
            exp = 0.85
        elif gap <= 2:
            exp = 0.6
        elif gap <= 3:
            exp = 0.35
        else:
            exp = 0.1
    if is_junior_title and not is_intern:
        exp = min(1.0, exp + 0.1)
    if is_senior:
        exp = min(exp, 0.35)
    signals["experience"] = round(exp, 3)

    # Language
    cand_langs = candidate_languages(profile)
    req_lang, lang_required = detect_required_language(job)
    if req_lang is None:
        lang = 1.0
    elif req_lang in cand_langs:
        lang = 1.0
    elif lang_required:
        lang = 0.0
    else:
        lang = 0.5  # mentioned but optional
    signals["language"] = round(lang, 3)
    signals["required_language"] = req_lang

    # Location
    loc, matched_loc, is_remote = location_match(job, location_cfgs)
    signals["location"] = round(loc, 3)
    signals["matched_location"] = matched_loc
    signals["remote"] = is_remote

    # Weighted base score
    base = (
        _WEIGHTS["skill"] * sk
        + _WEIGHTS["title"] * ttl
        + _WEIGHTS["experience"] * exp
        + _WEIGHTS["language"] * lang
        + _WEIGHTS["location"] * loc
    )
    # Salary nudges the score by up to +/-5 points without dominating fit.
    sal = salary_score(job, profile)
    signals["salary"] = round(sal, 3)
    score = base * 100 + (sal - 0.5) * 10
    score = max(0.0, min(100.0, score))

    # ---- Hard rules (override the score's tier, location-aware) ----
    hard_fail = False
    reason = None
    if req_lang and lang_required and req_lang not in cand_langs:
        hard_fail, reason = True, f"requires {req_lang}"
    elif is_intern:
        hard_fail, reason = True, "internship"
    elif req_years is not None and req_years > profile_years + 3:
        # >3y beyond the candidate is out of reach; a smaller gap is a "stretch"
        # the soft experience signal already discounts (lands in C/B, not F).
        hard_fail, reason = True, f"requires {req_years:g}y experience"
    elif is_senior:
        hard_fail, reason = True, "senior/lead role"

    # Out-of-target location: cap rather than fail (detection is fuzzy).
    location_capped = False
    if not hard_fail and location_cfgs and loc <= 0.2 and not is_remote:
        location_capped = True

    # Relevance cap: a job that matches neither the candidate's skills nor their
    # role family is the wrong job, even if it's English + in-target + the right
    # seniority. Without this such jobs floated to B purely on the default
    # experience/language/location credit (e.g. a hotel "Dining Server" → A).
    relevance_capped = not hard_fail and sk < 0.2 and ttl <= 0.3

    signals["matched_skills"] = matched
    signals["missing_skills"] = missing[:12]

    if hard_fail:
        tier = "F"
        score = min(score, TIER_SCORE["F"])
    else:
        tier = score_to_tier(score)
        if location_capped and TIER_ORDER.index(tier) < TIER_ORDER.index("C"):
            tier = "C"
            reason = "outside target locations"
        if relevance_capped and TIER_ORDER.index(tier) < TIER_ORDER.index("C"):
            tier = "C"
            reason = reason or "off-target role (no skill/title match)"

    return {
        "score": round(score, 1),
        "tier": tier,
        "hard_fail": hard_fail,
        "hard_fail_reason": reason,
        "signals": signals,
    }


def blend_with_llm(deterministic, llm_tier):
    """Fuse the deterministic match with the LLM's tier into a final result.

    - A deterministic hard-fail always wins (F): these are objective gates
      (language/experience/seniority) the LLM frequently gets wrong.
    - Otherwise blend numeric scores 60/40 (deterministic-leaning, because the
      LLM only sees a slice of the job and may be a small local model).
    Returns dict(final_tier, final_score, llm_tier, deterministic_tier).
    """
    det_score = deterministic["score"]
    det_tier = deterministic["tier"]

    if deterministic["hard_fail"]:
        return {
            "final_tier": "F",
            "final_score": round(min(det_score, TIER_SCORE["F"]), 1),
            "llm_tier": (llm_tier or "").upper() or None,
            "deterministic_tier": det_tier,
        }

    llm_norm = (llm_tier or "").strip().upper()
    if llm_norm in TIER_SCORE:
        blended = 0.6 * det_score + 0.4 * TIER_SCORE[llm_norm]
    else:
        blended = det_score
    blended = max(0.0, min(100.0, blended))

    return {
        "final_tier": score_to_tier(blended),
        "final_score": round(blended, 1),
        "llm_tier": llm_norm or None,
        "deterministic_tier": det_tier,
    }
