import json
import os
from datetime import date, timedelta
from django.shortcuts import render
from django.conf import settings
from django.db.models import Q, Prefetch, Case, When, Value, IntegerField, Count
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
    # Tiers filter (comma-separated, default to S,A,B,C)
    tiers_param = request.GET.get("tiers", "S,A,B,C")
    if tiers_param == "all":
        tiers_list = []
    else:
        tiers_list = [t.strip().upper() for t in tiers_param.split(",") if t.strip()]
        
    source_param = request.GET.get("source", "")
    lang_param = request.GET.get("language", "")
    date_param = request.GET.get("date", "all") # Default to all to ensure they see data
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
    
    # Extract jobs and attach ranking fields for the template
    jobs = []
    for ranking in rankings_qs:
        job = ranking.job
        job.match_tier = ranking.match_tier
        job.rank = ranking.rank
        job.jd_summary = ranking.jd_summary
        jobs.append(job)
            
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

    tiers_count = {t: 0 for t in ["S", "A", "B", "C"]}
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

    today_tiers_count = {t: 0 for t in ["S", "A", "B", "C"]}
    for item in by_tier_today:
        t = item["match_tier"]
        if t in today_tiers_count:
            today_tiers_count[t] = item["count"]

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
        },
        "filters": active_filters,
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

