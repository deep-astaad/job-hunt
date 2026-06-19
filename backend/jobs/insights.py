"""
Analytics functions extracted from web_views.py so they can be used by both
the legacy Django template view and the new REST API endpoints.
"""
import json
import logging
from collections import Counter
from datetime import date, timedelta

from django.db.models import Q

from .models import Job, JobRanking
from .parsers import normalize_skill

logger = logging.getLogger(__name__)


def _median(values):
    if not values:
        return 0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def _fmt_yen(value):
    return f"¥{value / 1_000_000:.1f}M"


TIERS = ["S", "A", "B", "C", "F"]


def _is_aggregate(profile_id):
    """'all' (or no id) means combine across every profile rather than filter to one."""
    return not profile_id or profile_id == "all"


def compute_stats(profile_id=None):
    """Overall counts + tier breakdown (per-profile, or aggregated for 'all') + today sub-stats."""
    today = date.today()

    total_jobs = Job.objects.count()
    active_jobs = Job.objects.filter(is_active=True).count()
    scraped_today = Job.objects.filter(scraped_at__date=today).count()
    formatted_today = Job.objects.filter(scraped_at__date=today, is_formatted=True).count()
    ranked_today = Job.objects.filter(scraped_at__date=today, is_ranked=True).count()

    from django.db.models import Count
    by_source = list(
        Job.objects.values("source").annotate(count=Count("id")).order_by("-count")
    )
    by_tier = list(
        JobRanking.objects.values("match_tier").annotate(count=Count("id")).order_by("match_tier")
    )

    tiers_count = {t: 0 for t in TIERS}
    today_tiers_count = {t: 0 for t in TIERS}

    # For a single profile, filter to it; for 'all', aggregate across every ranking.
    tier_qs = JobRanking.objects.all()
    if not _is_aggregate(profile_id):
        tier_qs = tier_qs.filter(profile_id=profile_id)

    for row in tier_qs.values("match_tier").annotate(count=Count("id")):
        t = row["match_tier"]
        if t in tiers_count:
            tiers_count[t] = row["count"]

    for row in (
        tier_qs.filter(job__scraped_at__date=today)
        .values("match_tier")
        .annotate(count=Count("id"))
    ):
        t = row["match_tier"]
        if t in today_tiers_count:
            today_tiers_count[t] = row["count"]

    return {
        "total": total_jobs,
        "active": active_jobs,
        "today_scraped": scraped_today,
        "today_formatted": formatted_today,
        "today_ranked": ranked_today,
        "by_source": by_source,
        "by_tier": by_tier,
        "tiers_count": tiers_count,
        "today_tiers_count": today_tiers_count,
    }


def compute_trending_tech(profile_id=None, tiers=None):
    """Top 8 tech stack items from filtered rankings (or all active jobs as fallback)."""
    tech_counter = Counter()

    # values_list pulls only the tech_stack column — never the heavy
    # description / full_description / raw_data fields that select_related drags in.
    if not _is_aggregate(profile_id):
        qs = JobRanking.objects.filter(profile_id=profile_id)
        if tiers:
            qs = qs.filter(match_tier__in=tiers)
        stacks = qs.values_list("job__tech_stack", flat=True)
    else:
        stacks = Job.objects.filter(is_active=True).values_list("tech_stack", flat=True)

    for stack in stacks:
        if stack and isinstance(stack, list):
            for tech in stack:
                if tech:
                    tech_counter[tech.strip()] += 1

    total = sum(tech_counter.values()) or 1
    result = []
    for name, count in tech_counter.most_common(8):
        result.append({
            "name": name,
            "count": count,
            "percentage": round((count / total) * 100),
        })
    return result


def compute_growth_insights(profile, profile_id=None, all_profiles=None):
    """
    Career-growth analytics. For a single candidate profile it returns
    skill_gap + Japanese ROI (both profile-specific) plus market trends, salary
    bands and company signals. When ``profile`` is None the caller asked for the
    combined 'all profiles' view: skill_gap / jp are skipped (they need a
    profile's skills) and the rest is aggregated across every ranking.

    ``all_profiles`` is accepted for backwards-compat with the legacy template
    view and is otherwise unused.
    """
    insights = {
        "skill_gap": [],
        "skill_gap_job_count": 0,
        "jp": None,
        "trends": None,
        "salary": None,
        "companies": [],
    }

    aggregate = profile is None
    if profile_id is None and profile:
        profile_id = profile.get("id")
    profile_skills = {normalize_skill(s) for s in (profile or {}).get("core_skills", []) if s}
    today = date.today()

    # ---- Pass 1: matched roles (one profile, or all of them) ----
    # .values() fetches only the columns we touch, avoiding the multi-MB
    # description / raw_data payloads that select_related("job") would load per row.
    relevant = JobRanking.objects.filter(
        match_tier__in=["S", "A", "B", "C"], job__is_active=True
    )
    if not aggregate:
        relevant = relevant.filter(profile_id=profile_id)
    relevant = relevant.values(
        "match_tier", "job__company", "job__salary_yen", "job__tech_stack", "job__title"
    )

    gap_counter = Counter()
    unlock_counter = Counter()
    unlock_samples = {}
    company_counter = Counter()
    skill_salary = {}
    overall_salaries = []
    relevant_count = 0

    for row in relevant:
        relevant_count += 1
        company_counter[row["job__company"] or "Unknown"] += 1

        yen = row["job__salary_yen"]
        if yen:
            overall_salaries.append(yen)

        stack = row["job__tech_stack"]
        if not (stack and isinstance(stack, list)):
            continue
        seen = set()
        for tech in stack:
            if not tech:
                continue
            key = normalize_skill(tech)
            if key in seen:
                continue
            seen.add(key)
            if yen:
                skill_salary.setdefault(tech.strip(), []).append(yen)
            # skill_gap is meaningless without a profile's skills to diff against.
            if aggregate or key in profile_skills:
                continue
            gap_counter[tech.strip()] += 1
            if row["match_tier"] != "S":
                unlock_counter[tech.strip()] += 1
                samples = unlock_samples.setdefault(tech.strip(), [])
                if len(samples) < 3:
                    samples.append(f"{row['job__title']} @ {row['job__company']}")

    insights["skill_gap_job_count"] = relevant_count
    for name, count in gap_counter.most_common(8):
        percentage = round((count / max(relevant_count, 1)) * 100)
        insights["skill_gap"].append({
            "name": name,
            "count": count,
            "percentage": percentage,
            "unlock_count": unlock_counter.get(name, 0),
            "samples": unlock_samples.get(name, []),
        })

    insights["companies"] = [
        {"name": c, "count": n} for c, n in company_counter.most_common(8)
    ]

    if len(overall_salaries) >= 3:
        high_paying = []
        for skill, vals in skill_salary.items():
            if len(vals) >= 2:
                avg = int(sum(vals) / len(vals))
                high_paying.append({
                    "name": skill,
                    "avg": avg,
                    "avg_display": _fmt_yen(avg),
                    "count": len(vals),
                })
        high_paying.sort(key=lambda x: x["avg"], reverse=True)
        insights["salary"] = {
            "count": len(overall_salaries),
            "median": _median(overall_salaries),
            "median_display": _fmt_yen(_median(overall_salaries)),
            "min_display": _fmt_yen(min(overall_salaries)),
            "max_display": _fmt_yen(max(overall_salaries)),
            "high_paying": high_paying[:6],
        }

    # ---- Pass 2: market trends (last 7d vs prior 7d) ----
    recent_counter = Counter()
    prior_counter = Counter()
    cutoff_recent = today - timedelta(days=7)
    for job in Job.objects.filter(
        scraped_at__date__gte=today - timedelta(days=14)
    ).values("tech_stack", "scraped_at"):
        stack = job["tech_stack"]
        if not (stack and isinstance(stack, list)):
            continue
        scraped = job["scraped_at"]
        d = scraped.date() if hasattr(scraped, "date") else scraped
        bucket = recent_counter if d >= cutoff_recent else prior_counter
        seen = set()
        for tech in stack:
            if not tech:
                continue
            key = normalize_skill(tech)
            if key in seen:
                continue
            seen.add(key)
            bucket[tech.strip()] += 1

    deltas = []
    for skill in set(recent_counter) | set(prior_counter):
        delta = recent_counter[skill] - prior_counter[skill]
        if delta != 0:
            deltas.append({"name": skill, "delta": delta})
    rising = sorted([d for d in deltas if d["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:5]
    falling = sorted([d for d in deltas if d["delta"] < 0], key=lambda x: x["delta"])[:5]
    if rising or falling:
        insights["trends"] = {"rising": rising, "falling": falling}

    # ---- Pass 3: Japanese ROI (profile-specific; skipped for the 'all' view) ----
    if aggregate:
        return insights

    GOOD_TIERS = ["S", "A", "B"]
    reachable = JobRanking.objects.filter(
        profile_id=profile_id, match_tier__in=GOOD_TIERS, job__is_active=True
    ).count()
    f_jp_rankings = (
        JobRanking.objects
        .filter(profile_id=profile_id, match_tier="F", job__is_active=True)
        .filter(Q(job__language="JP") | Q(job__jlpt_level__isnull=False))
        .values("llm_tier", "job__tech_stack", "job__jlpt_level")
    )
    locked = 0
    jlpt_levels = Counter()
    for row in f_jp_rankings:
        llm_tier = row["llm_tier"]
        if llm_tier in GOOD_TIERS:
            is_locked = True
        elif llm_tier is None:
            stack = row["job__tech_stack"] or []
            is_locked = bool({normalize_skill(t) for t in stack if t} & profile_skills)
        else:
            is_locked = False
        if is_locked:
            locked += 1
            jlpt_levels[row["job__jlpt_level"] or 2] += 1

    relevant_total = locked + reachable
    active_total = Job.objects.filter(is_active=True).count()
    jp_total = Job.objects.filter(is_active=True, language="JP").count()
    c = jlpt_levels
    insights["jp"] = {
        "locked": locked,
        "reachable": reachable,
        "relevant_total": relevant_total,
        "locked_pct": round((locked / relevant_total) * 100) if relevant_total else 0,
        "unlock_pct": round((locked / reachable) * 100) if reachable else 0,
        "jp_total": jp_total,
        "active_total": active_total,
        "jp_market_pct": round((jp_total / active_total) * 100) if active_total else 0,
        "jlpt": {
            "n3": c[3] + c[4] + c[5],
            "n2": c[2] + c[3] + c[4] + c[5],
            "n1": locked,
        },
    }
    return insights


def get_cached_dashboard(profile_id: str, profiles: list):
    """Return dashboard payload from Redis cache or compute fresh."""
    import json as _json
    try:
        import sys
        import os
        # config.py lives at repo root — add it if needed
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        from config import get_redis_client
        r = get_redis_client()
        cache_key = f"dashboard_cache:{profile_id}"
        if r:
            raw = r.get(cache_key)
            if raw:
                return _json.loads(raw)
    except Exception:
        r = None
        cache_key = None

    # Cache miss — compute
    profile = next((p for p in profiles if p.get("id") == profile_id), None)
    stats = compute_stats(profile_id)
    trending = compute_trending_tech(profile_id, tiers=["S", "A", "B", "C"])
    growth = compute_growth_insights(profile, profile_id=profile_id)

    payload = {
        "stats": stats,
        "trending_tech": trending,
        "insights": growth,
    }

    try:
        if r and cache_key:
            r.set(cache_key, _json.dumps(payload), ex=300)
    except Exception:
        pass

    return payload
