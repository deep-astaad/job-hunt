import json
import os
import re
from collections import Counter
from datetime import date, timedelta
from django.shortcuts import render
from django.conf import settings
from django.db.models import Q, Case, When, Value, IntegerField, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Job, JobRanking

def load_profiles():
    """Load candidate profiles from the workspace JSON file."""
    profiles_path = os.path.join(settings.BASE_DIR.parent, "user-profiles.json")
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def load_actor_configs():
    """Load Apify scraper actor configurations."""
    config_path = os.path.join(settings.BASE_DIR.parent, "actor-config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _norm_skill(value):
    """Normalize a skill/tech name for case-insensitive comparison."""
    return str(value).strip().lower()


def _parse_salary_to_yen(text):
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
    if rep < 1000:  # likely hourly/garbage, not an annual figure
        return None
    return int(rep)


def _required_jlpt_level(text):
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


def compute_growth_insights(profile):
    """Career-growth analytics for a candidate profile.

    1. Skill gap (+ what each gap skill could lift) -- a directed study list.
    2. Japanese ROI (+ JLPT-threshold simulation) -- cost of the language gate.
    3. Market trends -- skills rising/cooling over the last 7d vs prior 7d.
    4. Salary bands -- estimated pay of matched roles + highest-paying skills.
    5. Company hiring signals -- companies most active among your matches.
    """
    insights = {
        "skill_gap": [], "skill_gap_job_count": 0,
        "jp": None, "trends": None, "salary": None, "companies": [],
    }
    if not profile:
        return insights

    profile_skills = {_norm_skill(s) for s in profile.get("core_skills", []) if s}
    today = date.today()

    # ---- Pass 1: profile matched roles (S/A/B/C) -> gap, unlock, salary, companies ----
    relevant = (
        JobRanking.objects
        .filter(profile_id=profile["id"], match_tier__in=["S", "A", "B", "C"])
        .select_related("job")
    )
    gap_counter = Counter()
    unlock_counter = Counter()   # gap skill -> # of non-S matched roles needing it
    unlock_samples = {}          # gap skill -> ["Title @ Company", ...]
    company_counter = Counter()
    skill_salary = {}            # skill -> [yen, ...]
    overall_salaries = []
    relevant_count = 0

    for ranking in relevant:
        job = ranking.job
        relevant_count += 1
        company_counter[job.company or "Unknown"] += 1

        yen = _parse_salary_to_yen(job.salary)
        if yen:
            overall_salaries.append(yen)

        stack = job.tech_stack
        if not (stack and isinstance(stack, list)):
            continue
        seen = set()
        for tech in stack:
            if not tech:
                continue
            key = _norm_skill(tech)
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
            "name": name, "count": count, "percentage": percentage,
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
                    "name": skill, "avg": avg,
                    "avg_display": _fmt_yen(avg), "count": len(vals),
                })
        high_paying.sort(key=lambda x: x["avg"], reverse=True)
        insights["salary"] = {
            "count": len(overall_salaries),
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
            key = _norm_skill(tech)
            if key in seen:
                continue
            seen.add(key)
            bucket[tech.strip()] += 1

    deltas = []
    for skill in set(recent_counter) | set(prior_counter):
        delta = recent_counter[skill] - prior_counter[skill]
        if delta != 0:
            deltas.append({"name": skill, "delta": delta})
    rising = sorted([d for d in deltas if d["delta"] > 0],
                    key=lambda x: x["delta"], reverse=True)[:5]
    falling = sorted([d for d in deltas if d["delta"] < 0],
                     key=lambda x: x["delta"])[:5]
    if rising or falling:
        insights["trends"] = {"rising": rising, "falling": falling}

    # ---- Pass 3: Japanese ROI + JLPT-threshold simulation ----
    locked = reachable = jp_total = active_total = 0
    jlpt_levels = Counter()  # required level among skill-relevant, JP-locked roles
    for job in Job.objects.filter(is_active=True).values(
        "tech_stack", "language", "title", "description"
    ):
        active_total += 1
        is_jp = (job["language"] or "").upper() == "JP"
        if is_jp:
            jp_total += 1
        stack = job["tech_stack"]
        overlap = set()
        if stack and isinstance(stack, list):
            overlap = {_norm_skill(t) for t in stack if t} & profile_skills
        if not overlap:
            continue
        if is_jp:
            locked += 1
            level = _required_jlpt_level(f"{job['title']} {job['description']}") or 2
            jlpt_levels[level] += 1
        else:
            reachable += 1

    relevant_total = locked + reachable
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

def dashboard(request):
    """Render the main jobs dashboard and filter results."""
    profiles = load_profiles()
    
    # 1. Retrieve stats
    total_jobs = Job.objects.count()
    active_jobs = Job.objects.filter(is_active=True).count()
    
    # Today's jobs
    scraped_today = Job.objects.filter(scraped_at__date=date.today()).count()
    formatted_today = Job.objects.filter(scraped_at__date=date.today(), is_formatted=True).count()
    ranked_today = Job.objects.filter(scraped_at__date=date.today(), is_ranked=True).count()
    
    # Breakdowns
    by_source = list(
        Job.objects.values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    by_tier = list(
        JobRanking.objects.values("match_tier")
        .annotate(count=Count("id"))
        .order_by("match_tier")
    )
    
    # 2. Handle profile selection
    selected_profile_id = request.GET.get("profile_id")
    # Fallback to first profile if not provided
    if not selected_profile_id and profiles:
        selected_profile_id = profiles[0]["id"]
        
    selected_profile = None
    if profiles:
        for p in profiles:
            if p["id"] == selected_profile_id:
                selected_profile = p
                break
        if not selected_profile:
            selected_profile = profiles[0]
            selected_profile_id = selected_profile["id"]
            
    # 3. Handle filters
    # Tiers filter (comma-separated, default to S,A,B)
    tiers_param = request.GET.get("tiers", "S,A,B")
    if tiers_param == "all":
        tiers_list = []
    else:
        tiers_list = [t.strip().upper() for t in tiers_param.split(",") if t.strip()]
        
    source_param = request.GET.get("source", "")
    lang_param = request.GET.get("language", "")
    date_param = request.GET.get("date", "today") # Default to today
    q_param = request.GET.get("q", "").strip()
    
    # Base Queryset: Fetch rankings for this profile, select related Job to avoid N+1
    rankings_qs = JobRanking.objects.filter(profile_id=selected_profile_id).select_related("job")
    
    # Filter by Tiers
    if tiers_list:
        rankings_qs = rankings_qs.filter(match_tier__in=tiers_list)
        
    # Apply Job-level filters
    if source_param:
        rankings_qs = rankings_qs.filter(job__source=source_param)
        
    if lang_param:
        rankings_qs = rankings_qs.filter(job__language=lang_param)
        
    if date_param == "today":
        rankings_qs = rankings_qs.filter(job__scraped_at__date=date.today())
    elif date_param == "3days":
        rankings_qs = rankings_qs.filter(job__scraped_at__date__gte=date.today() - timedelta(days=3))
    elif date_param == "7days":
        rankings_qs = rankings_qs.filter(job__scraped_at__date__gte=date.today() - timedelta(days=7))
        
    if q_param:
        rankings_qs = rankings_qs.filter(
            Q(job__title__icontains=q_param) |
            Q(job__company__icontains=q_param) |
            Q(job__description__icontains=q_param)
        )
        
    # Custom sorting (S, A, B, C, F then Rank)
    tier_order = Case(
        When(match_tier="S", then=Value(0)),
        When(match_tier="A", then=Value(1)),
        When(match_tier="B", then=Value(2)),
        When(match_tier="C", then=Value(3)),
        When(match_tier="F", then=Value(4)),
        default=Value(99),
        output_field=IntegerField(),
    )
    
    rankings_qs = rankings_qs.annotate(tier_val=tier_order).order_by("tier_val", "rank")
    
    # Calculate total matches first (from the unpaginated QuerySet)
    total_matches = rankings_qs.count()

    # Calculate trending tech stack from all matching jobs before slicing
    tech_counter = Counter()
    for ranking in rankings_qs:
        job_tech_stack = ranking.job.tech_stack
        if job_tech_stack and isinstance(job_tech_stack, list):
            for tech in job_tech_stack:
                if tech:
                    tech_counter[tech.strip()] += 1

    # Fallback to all active jobs if no tech stack info exists in filtered jobs
    if not tech_counter:
        for job in Job.objects.filter(is_active=True):
            if job.tech_stack and isinstance(job.tech_stack, list):
                for tech in job.tech_stack:
                    if tech:
                        tech_counter[tech.strip()] += 1

    trending_tech = []
    total_matching_jobs = total_matches
    for name, count in tech_counter.most_common(6):
        percentage = round((count / max(total_matching_jobs, 1)) * 100) if total_matching_jobs > 0 else 0
        if total_matching_jobs == 0:
            total_active = Job.objects.filter(is_active=True).count()
            percentage = round((count / max(total_active, 1)) * 100) if total_active > 0 else 0
        trending_tech.append({
            "name": name,
            "count": count,
            "percentage": percentage
        })

    # Apply pagination slicing
    page_size = 20
    try:
        page = int(request.GET.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    start = (page - 1) * page_size
    end = start + page_size
    paginated_rankings = rankings_qs[start:end]
    has_more = end < total_matches

    # Extract paginated jobs and attach ranking fields for the template
    jobs = []
    for ranking in paginated_rankings:
        job = ranking.job
        job.match_tier = ranking.match_tier
        job.rank = ranking.rank
        job.jd_summary = ranking.jd_summary
        jobs.append(job)

    # Handle AJAX requests for infinite scroll
    if request.GET.get("ajax") == "1":
        from django.template.loader import render_to_string
        html_content = render_to_string("jobs/job_cards_list.html", {"jobs": jobs}, request=request)
        return JsonResponse({
            "html": html_content,
            "has_more": has_more
        })

    # Calculate tier counts for the selected profile
    by_tier_profile = []
    if selected_profile_id:
        by_tier_profile = list(
            JobRanking.objects.filter(profile_id=selected_profile_id)
            .values("match_tier")
            .annotate(count=Count("id"))
            .order_by("match_tier")
        )
    else:
        by_tier_profile = by_tier

    tiers_count = {t: 0 for t in ["S", "A", "B", "C", "F"]}
    for item in by_tier_profile:
        t = item["match_tier"]
        if t in tiers_count:
            tiers_count[t] = item["count"]

    # Calculate today's tier counts for the selected profile
    by_tier_today = []
    if selected_profile_id:
        by_tier_today = list(
            JobRanking.objects.filter(
                profile_id=selected_profile_id,
                job__scraped_at__date=date.today()
            )
            .values("match_tier")
            .annotate(count=Count("id"))
            .order_by("match_tier")
        )

    today_tiers_count = {t: 0 for t in ["S", "A", "B", "C", "F"]}
    for item in by_tier_today:
        t = item["match_tier"]
        if t in today_tiers_count:
            today_tiers_count[t] = item["count"]

    # Career-growth insights (skill gap + Japanese ROI) for the selected profile
    insights = compute_growth_insights(selected_profile)

    # Compile filters for context
    active_filters = {
        "profile_id": selected_profile_id,
        "tiers": tiers_param,
        "source": source_param,
        "language": lang_param,
        "date": date_param,
        "q": q_param,
    }
    
    context = {
        "profiles": profiles,
        "selected_profile": selected_profile,
        "jobs": jobs,
        "total_matches": total_matches,
        "has_more": has_more,
        "stats": {
            "total": total_jobs,
            "active": active_jobs,
            "today": scraped_today,
            "formatted": formatted_today,
            "ranked": ranked_today,
            "by_source": by_source,
            "by_tier": by_tier,
            "tiers_count": tiers_count,
            "today_scraped": scraped_today,
            "today_formatted": formatted_today,
            "today_ranked": ranked_today,
            "today_tiers_count": today_tiers_count,
            "trending_tech": trending_tech,
        },
        "filters": active_filters,
        "insights": insights,
        "source_choices": Job.SOURCE_CHOICES,
        "language_choices": Job.LANGUAGE_CHOICES,
    }
    return render(request, "jobs/dashboard.html", context)

@require_POST
def trigger_scrape(request):
    """Trigger the scraping and ranking pipeline asynchronously via Celery worker."""
    import sys
    if str(settings.BASE_DIR.parent) not in sys.path:
        sys.path.append(str(settings.BASE_DIR.parent))
        
    try:
        from tasks.pipeline import run_pipeline
        actor_configs = load_actor_configs()
        profiles = load_profiles()
        profile_ids = [p["id"] for p in profiles]
        
        if not actor_configs:
            return JsonResponse({
                "status": "error",
                "message": "No Apify actor configurations found in actor-config.json."
            }, status=400)
            
        target_source = request.POST.get("source", "").strip()
        if target_source:
            actor_configs = [c for c in actor_configs if c.get("source") == target_source]
            if not actor_configs:
                return JsonResponse({
                    "status": "error",
                    "message": f"No actor config found with source '{target_source}'."
                }, status=400)
            
        # Dispatch the Celery task
        task = run_pipeline.delay(actor_configs, profile_ids)
        return JsonResponse({
            "status": "success",
            "task_id": task.id,
            "message": "Celery scraping pipeline task triggered successfully."
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@require_POST
def trigger_processing(request):
    """Trigger processing of all unformatted and unranked jobs via Celery worker."""
    if not request.user.is_staff:
        return JsonResponse({
            "status": "error",
            "message": "Forbidden: Administrator permissions required."
        }, status=403)

    import sys
    if str(settings.BASE_DIR.parent) not in sys.path:
        sys.path.append(str(settings.BASE_DIR.parent))

    try:
        from tasks.pipeline import process_unprocessed_jobs_task
        profiles = load_profiles()
        profile_ids = [p["id"] for p in profiles]

        # Dispatch the Celery task
        task = process_unprocessed_jobs_task.delay(profile_ids)
        return JsonResponse({
            "status": "success",
            "task_id": task.id,
            "message": "Format and rank pipeline task triggered successfully."
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

