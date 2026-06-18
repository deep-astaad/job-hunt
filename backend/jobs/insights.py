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


def compute_stats(profile_id=None):
    """Overall counts + per-profile tier breakdown + today sub-stats."""
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

    tiers_count = {t: 0 for t in ["S", "A", "B", "C", "F"]}
    today_tiers_count = {t: 0 for t in ["S", "A", "B", "C", "F"]}

    if profile_id:
        for row in JobRanking.objects.filter(profile_id=profile_id).values("match_tier").annotate(count=Count("id")):
            t = row["match_tier"]
            if t in tiers_count:
                tiers_count[t] = row["count"]

        for row in (
            JobRanking.objects
            .filter(profile_id=profile_id, job__scraped_at__date=today)
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

    if profile_id:
        qs = JobRanking.objects.filter(profile_id=profile_id).select_related("job")
        if tiers:
            qs = qs.filter(match_tier__in=tiers)
        for ranking in qs:
            stack = ranking.job.tech_stack
            if stack and isinstance(stack, list):
                for tech in stack:
                    if tech:
                        tech_counter[tech.strip()] += 1
    else:
        for job in Job.objects.filter(is_active=True).only("tech_stack"):
            stack = job.tech_stack
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


def compute_growth_insights(profile):
    """
    Career-growth analytics for a candidate profile.
    Returns: skill_gap, jp ROI, market trends, salary bands, company signals.
    """
    insights = {
        "skill_gap": [],
        "skill_gap_job_count": 0,
        "jp": None,
        "trends": None,
        "salary": None,
        "companies": [],
    }
    if not profile:
        return insights

    profile_skills = {normalize_skill(s) for s in profile.get("core_skills", []) if s}
    today = date.today()

    # ---- Pass 1: profile matched roles ----
    relevant = (
        JobRanking.objects
        .filter(profile_id=profile["id"], match_tier__in=["S", "A", "B", "C"], job__is_active=True)
        .select_related("job")
    )
    gap_counter = Counter()
    unlock_counter = Counter()
    unlock_samples = {}
    company_counter = Counter()
    skill_salary = {}
    overall_salaries = []
    relevant_count = 0

    for ranking in relevant:
        job = ranking.job
        relevant_count += 1
        company_counter[job.company or "Unknown"] += 1

        yen = job.salary_yen
        if yen:
            overall_salaries.append(yen)

        stack = job.tech_stack
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
            if key in profile_skills:
                continue
            gap_counter[tech.strip()] += 1
            if ranking.match_tier != "S":
                unlock_counter[tech.strip()] += 1
                samples = unlock_samples.setdefault(tech.strip(), [])
                if len(samples) < 3:
                    samples.append(f"{job.title} @ {job.company}")

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

    # ---- Pass 3: Japanese ROI ----
    GOOD_TIERS = ["S", "A", "B"]
    reachable = JobRanking.objects.filter(
        profile_id=profile["id"], match_tier__in=GOOD_TIERS, job__is_active=True
    ).count()
    f_jp_rankings = (
        JobRanking.objects
        .filter(profile_id=profile["id"], match_tier="F", job__is_active=True)
        .filter(Q(job__language="JP") | Q(job__jlpt_level__isnull=False))
        .select_related("job")
    )
    locked = 0
    jlpt_levels = Counter()
    for ranking in f_jp_rankings:
        job = ranking.job
        if ranking.llm_tier in GOOD_TIERS:
            is_locked = True
        elif ranking.llm_tier is None:
            stack = job.tech_stack or []
            is_locked = bool({normalize_skill(t) for t in stack if t} & profile_skills)
        else:
            is_locked = False
        if is_locked:
            locked += 1
            jlpt_levels[job.jlpt_level or 2] += 1

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
    growth = compute_growth_insights(profile)

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
