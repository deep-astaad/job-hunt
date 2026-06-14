"""Pure-Python parsers for deriving structured fields from free-text job data.

Kept free of Django imports so both models.py (at save time) and web_views.py
(for analytics) can use them without a circular import.
"""
import re


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
