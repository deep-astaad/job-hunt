from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch
from jobs.models import Job, JobRanking


class JobModelTests(TestCase):
    def setUp(self):
        self.job = Job.objects.create(
            title="Software Engineer",
            company="Google",
            url="https://google.com/jobs/1",
            url_hash="hash1",
            is_formatted=False,
            is_ranked=False,
        )

    def test_save_resets_is_ranked_when_unformatted(self):
        # Even if is_ranked is set to True, if is_formatted is False, it should reset to False on save
        self.job.is_ranked = True
        self.job.save()
        self.assertFalse(self.job.is_ranked)

    def test_save_keeps_is_ranked_when_formatted(self):
        self.job.is_formatted = True
        self.job.is_ranked = True
        self.job.save()
        self.assertTrue(self.job.is_ranked)

    def test_ranking_save_sets_job_is_ranked(self):
        self.job.is_formatted = True
        self.job.save()
        self.assertFalse(self.job.is_ranked)

        # Create a ranking
        ranking = JobRanking.objects.create(
            job=self.job,
            profile_id="test_profile",
            profile_title="Test Profile",
            match_tier="A",
            rank=1,
            jd_summary="Summary text"
        )
        # Fetch fresh job from database
        self.job.refresh_from_db()
        self.assertTrue(self.job.is_ranked)


class JobProcessingViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("jobs_web:trigger_processing")

        self.regular_user = User.objects.create_user(
            username="regular", password="password", is_staff=False
        )
        self.admin_user = User.objects.create_user(
            username="admin", password="password", is_staff=True
        )

    def test_trigger_processing_anonymous_forbidden(self):
        # For POST requests, the staff_member_required decorator redirects to admin login
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Forbidden", response.json().get("message", ""))

    def test_trigger_processing_regular_user_forbidden(self):
        self.client.login(username="regular", password="password")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Forbidden", response.json().get("message", ""))

    @patch("tasks.pipeline.process_unprocessed_jobs_task.delay")
    def test_trigger_processing_admin_success(self, mock_delay):
        mock_delay.return_value.id = "mock-task-id-123"
        self.client.login(username="admin", password="password")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("task_id"), "mock-task-id-123")
        mock_delay.assert_called_once()


class CeleryTaskTests(TestCase):
    def setUp(self):
        # 1. Unformatted job (should format and rank)
        self.unformatted_job = Job.objects.create(
            title="Unformatted Engineer",
            company="Company A",
            url="https://comp-a.com/job",
            url_hash="hash_a",
            is_formatted=False,
        )
        # 2. Formatted but unranked job (should rank directly)
        self.unranked_job = Job.objects.create(
            title="Unranked Engineer",
            company="Company B",
            url="https://comp-b.com/job",
            url_hash="hash_b",
            is_formatted=True,
            is_ranked=False,
        )
        # 3. Already fully processed job (should be skipped)
        self.processed_job = Job.objects.create(
            title="Processed Engineer",
            company="Company C",
            url="https://comp-c.com/job",
            url_hash="hash_c",
            is_formatted=True,
            is_ranked=True,
        )

    @patch("redis.Redis.from_url")
    @patch("tasks.pipeline._load_profiles_for_ranking")
    @patch("celery.chain")
    @patch("tasks.ranking.rank_job_multi_profile.apply_async")
    def test_process_unprocessed_jobs_task(self, mock_rank_apply_async, mock_chain,
                                           mock_load_profiles, mock_redis_from_url):
        mock_load_profiles.return_value = [{"id": "profile_1"}]
        # Isolate from any real Redis: the per-job dedup lock always "acquires".
        mock_redis_from_url.return_value.set.return_value = True

        from tasks.pipeline import process_unprocessed_jobs_task
        
        result = process_unprocessed_jobs_task()
        
        self.assertEqual(result.get("unformatted_processed"), 1)
        self.assertEqual(result.get("unranked_processed"), 1)
        
        # Verify formatting + ranking chain was triggered for unformatted job
        mock_chain.assert_called_once()
        
        # Verify rank task was called directly for unranked job
        mock_rank_apply_async.assert_called_once()


class JobStatsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.job1 = Job.objects.create(
            title="Engineer A",
            company="Company A",
            url="https://a.com",
            url_hash="hasha",
            is_formatted=True,
            is_ranked=True,
            tech_stack=["Python", "Django", "React"],
        )
        self.job2 = Job.objects.create(
            title="Engineer B",
            company="Company B",
            url="https://b.com",
            url_hash="hashb",
            is_formatted=True,
            is_ranked=False,
            tech_stack=["Python", "Go"],
        )
        self.ranking = JobRanking.objects.create(
            job=self.job1,
            profile_id="backend_platform_engineer",
            profile_title="Backend Platform Engineer",
            match_tier="S",
            rank=1,
        )

    def test_dashboard_stats(self):
        # We can call the dashboard url
        url = reverse("jobs_web:dashboard")
        # Passing profile_id in GET params to match test setup
        response = self.client.get(f"{url}?profile_id=backend_platform_engineer")
        self.assertEqual(response.status_code, 200)
        stats = response.context["stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["formatted"], 2)
        self.assertEqual(stats["ranked"], 1)
        self.assertEqual(stats["tiers_count"]["S"], 1)
        self.assertEqual(stats["tiers_count"]["A"], 0)

        # Check trending_tech calculation for filtered jobs (only job1 is ranked for backend_platform_engineer)
        trending_tech = stats["trending_tech"]
        self.assertTrue(len(trending_tech) > 0)
        # Python, Django, React should be at the top with 100% since only 1 job is matched
        python_tech = next(t for t in trending_tech if t["name"] == "Python")
        self.assertEqual(python_tech["count"], 1)
        self.assertEqual(python_tech["percentage"], 100)

    def test_dashboard_stats_fallback(self):
        # When profile_id has no ranked jobs (like cloud_devops_architect), it falls back to all active jobs
        url = reverse("jobs_web:dashboard")
        response = self.client.get(f"{url}?profile_id=cloud_devops_architect")
        self.assertEqual(response.status_code, 200)
        stats = response.context["stats"]
        
        # Falls back to all active jobs: job1 & job2.
        trending_tech = stats["trending_tech"]
        python_tech = next(t for t in trending_tech if t["name"] == "Python")
        self.assertEqual(python_tech["count"], 2)
        self.assertEqual(python_tech["percentage"], 100)

        go_tech = next(t for t in trending_tech if t["name"] == "Go")
        self.assertEqual(go_tech["count"], 1)
        self.assertEqual(go_tech["percentage"], 50)

    def test_api_stats(self):
        url = reverse("job-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_jobs"], 2)
        self.assertEqual(data["formatted_jobs"], 2)
        self.assertEqual(data["ranked_jobs"], 1)


class DashboardInfiniteScrollTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create 25 jobs and rankings for backend_platform_engineer
        for i in range(25):
            job = Job.objects.create(
                title=f"Engineer {i}",
                company=f"Company {i}",
                url=f"https://example.com/job/{i}",
                url_hash=f"hash_{i}",
                is_formatted=True,
                is_ranked=True,
            )
            JobRanking.objects.create(
                job=job,
                profile_id="backend_platform_engineer",
                profile_title="Backend Platform Engineer",
                match_tier="S",
                rank=i + 1,
            )

    @patch("jobs.web_views.load_profiles")
    def test_dashboard_pagination_first_page(self, mock_load_profiles):
        mock_load_profiles.return_value = [{"id": "backend_platform_engineer", "title": "Backend Platform Engineer"}]
        url = reverse("jobs_web:dashboard")
        response = self.client.get(f"{url}?profile_id=backend_platform_engineer")
        self.assertEqual(response.status_code, 200)
        
        # Only 20 jobs should be rendered/passed in context
        self.assertEqual(len(response.context["jobs"]), 20)
        self.assertEqual(response.context["total_matches"], 25)
        self.assertTrue(response.context["has_more"])

    @patch("jobs.web_views.load_profiles")
    def test_dashboard_pagination_ajax_page(self, mock_load_profiles):
        mock_load_profiles.return_value = [{"id": "backend_platform_engineer", "title": "Backend Platform Engineer"}]
        url = reverse("jobs_web:dashboard")
        
        # Request page 2 with ajax=1
        response = self.client.get(f"{url}?profile_id=backend_platform_engineer&page=2&ajax=1")
        self.assertEqual(response.status_code, 200)
        
        # It should return a JsonResponse
        data = response.json()
        self.assertIn("html", data)
        self.assertFalse(data["has_more"])
        
        # The HTML should contain 5 job cards
        self.assertEqual(data["html"].count("class=\"job-card"), 5)


class LocationAndScoringTests(TestCase):
    """Covers the new location fields, region filter, and ranking score plumbing."""

    def setUp(self):
        self.client = Client()

    def test_job_bulk_create_accepts_location_and_derives_region(self):
        resp = self.client.post(
            reverse("job-bulk-create"),
            data=[{
                "url": "https://co.example/jp1",
                "title": "Backend Engineer",
                "company": "Acme",
                "location": "Tokyo, Japan",
                "is_formatted": True,
            }],
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (200, 201))
        job = Job.objects.get(url="https://co.example/jp1")
        self.assertEqual(job.location, "Tokyo, Japan")
        self.assertEqual(job.region, "japan")
        self.assertEqual(job.country, "JP")

    def test_bulk_create_restub_does_not_wipe_formatted_job(self):
        """A blank re-scrape stub must not overwrite formatted data or reset
        is_formatted/is_ranked (C2): that would force a costly re-format/re-rank."""
        import hashlib as _hashlib
        from .parsers import normalize_url as _norm
        url1 = "https://co.example/dedup1"
        hash1 = _hashlib.sha256(_norm(url1).encode()).hexdigest()
        # Job already scraped, formatted, and ranked on a prior run.
        job = Job.objects.create(
            title="Backend Engineer", company="Acme",
            url=_norm(url1), url_hash=hash1,
            description="Real formatted description.",
            full_description="Full formatted JD.",
            tech_stack=["Python", "Django"],
            language="EN", experience_required="3+ years",
            is_formatted=True,
        )
        JobRanking.objects.create(
            job=job, profile_id="p1", match_tier="A", match_score=80, rank=10,
        )
        job.refresh_from_db()
        self.assertTrue(job.is_ranked)

        # The poller re-sends a blank stub for the same URL.
        resp = self.client.post(
            reverse("job-bulk-create"),
            data=[{
                "url": "https://co.example/dedup1",
                "title": "Backend Engineer",
                "company": "Acme",
                "source": "linkedin",
                "description": "",
                "full_description": "",
                "tech_stack": None,
            }],
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (200, 201))

        job.refresh_from_db()
        self.assertEqual(job.description, "Real formatted description.")
        self.assertEqual(job.full_description, "Full formatted JD.")
        self.assertEqual(job.tech_stack, ["Python", "Django"])
        self.assertTrue(job.is_formatted)
        self.assertTrue(job.is_ranked)

    def test_bulk_create_formatted_payload_still_updates(self):
        """The formatter's bulk_create fallback (real data, is_formatted=True)
        must still update a previously-stubbed row."""
        import hashlib as _hashlib
        from .parsers import normalize_url as _norm
        url2 = "https://co.example/dedup2"
        hash2 = _hashlib.sha256(_norm(url2).encode()).hexdigest()
        Job.objects.create(
            title="Backend Engineer", company="Acme",
            url=_norm(url2), url_hash=hash2,
            description="", is_formatted=False,
        )
        resp = self.client.post(
            reverse("job-bulk-create"),
            data=[{
                "url": "https://co.example/dedup2",
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Now formatted.",
                "tech_stack": ["Go"],
                "is_formatted": True,
            }],
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (200, 201))
        job = Job.objects.get(url="https://co.example/dedup2")
        self.assertEqual(job.description, "Now formatted.")
        self.assertEqual(job.tech_stack, ["Go"])
        self.assertTrue(job.is_formatted)

    def test_remote_is_detected_on_save(self):
        job = Job.objects.create(
            title="Backend Engineer (Fully Remote)", company="Acme",
            url="https://co.example/r1", url_hash="rh1",
            description="Work from home, distributed team.",
        )
        self.assertTrue(job.is_remote)

    def test_ranking_bulk_create_persists_score_fields(self):
        job = Job.objects.create(
            title="Backend Engineer", company="Acme",
            url="https://co.example/s1", url_hash="sh1", is_formatted=True,
        )
        resp = self.client.post(
            reverse("jobranking-bulk-create"),
            data=[{
                "job_id": job.id, "profile_id": "p1", "match_tier": "A",
                "llm_tier": "S", "deterministic_tier": "A", "match_score": 77,
                "signals": {"skill": 0.9}, "rank": 23, "jd_summary": "x",
            }],
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (200, 201))
        r = JobRanking.objects.get(job=job, profile_id="p1")
        self.assertEqual(r.match_score, 77)
        self.assertEqual(r.deterministic_tier, "A")
        self.assertEqual(r.signals, {"skill": 0.9})

    def test_dashboard_region_filter_renders(self):
        job = Job.objects.create(
            title="Backend Engineer", company="Acme",
            url="https://co.example/d1", url_hash="dh1",
            is_formatted=True, location="Tokyo, Japan",
        )
        JobRanking.objects.create(
            job=job, profile_id="backend_platform_engineer", match_tier="A",
            match_score=80, rank=20,
        )
        resp = self.client.get(
            reverse("jobs_web:dashboard")
            + "?profile_id=backend_platform_engineer&region=japan&tiers=all&date=all"
        )
        self.assertEqual(resp.status_code, 200)
        # Score badge is rendered on the card.
        self.assertContains(resp, "/100")


