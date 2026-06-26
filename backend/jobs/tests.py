import requests
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch, MagicMock
from jobs.models import Job, JobApplicationStatus, JobRanking


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


class DiscordAlertMarkingTests(TestCase):
    """post_single_job_to_discord must only mark alert_sent on a confirmed-OK post."""

    def _job_and_rankings(self):
        return ({"id": 7, "region": "japan", "title": "BE", "company": "X"},
                [{"match_tier": "S", "profile_id": "p1", "jd_summary": "x"}])

    @patch("outputs.DISCORD_WEBHOOK_URL_JAPAN", "https://discord.test/webhook")
    @patch("outputs.requests.post")
    def test_failed_discord_post_does_not_mark_sent(self, mock_post):
        # Webhook returns e.g. 429 -> raise_for_status() raises -> no mark.
        mock_post.return_value.raise_for_status.side_effect = requests.RequestException("429")
        from outputs import ExportHandler
        job, rankings = self._job_and_rankings()
        ExportHandler.post_single_job_to_discord(job, rankings)
        # Only the webhook POST happened; mark_alerts_sent was never called.
        self.assertEqual(mock_post.call_count, 1)

    @patch("outputs.DISCORD_WEBHOOK_URL_JAPAN", "https://discord.test/webhook")
    @patch("outputs.requests.post")
    def test_ok_discord_post_marks_sent(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        from outputs import ExportHandler
        job, rankings = self._job_and_rankings()
        ExportHandler.post_single_job_to_discord(job, rankings)
        # Webhook POST + mark_alerts_sent POST.
        self.assertEqual(mock_post.call_count, 2)
        self.assertIn("mark_alerts_sent", mock_post.call_args_list[1].args[0])


class PrescreenPersistTests(TestCase):
    """_persist_prescreen_f must be atomic: rankings first, flags only after."""

    def _results(self):
        return [{"profile_id": "p1", "hard_fail_reason": "requires japanese", "signals": {}}]

    @patch("tasks.pipeline.req.post")
    def test_rankings_failure_returns_false_and_leaves_flags_untouched(self, mock_post):
        # Discord/API ranking POST fails -> must NOT mark the job formatted.
        mock_post.return_value.raise_for_status.side_effect = Exception("500")
        from tasks.pipeline import _persist_prescreen_f

        persister = MagicMock()
        job = {"id": 123}
        ok = _persist_prescreen_f(job, self._results(), persister)

        self.assertFalse(ok)
        persister.update_job.assert_not_called()  # no formatted-but-unranked orphan

    @patch("tasks.pipeline.req.post")
    def test_success_marks_formatted_and_ranked_atomically(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        from tasks.pipeline import _persist_prescreen_f

        persister = MagicMock()
        job = {"id": 123}
        ok = _persist_prescreen_f(job, self._results(), persister)

        self.assertTrue(ok)
        persister.update_job.assert_called_once_with(
            123, {"is_formatted": True, "is_ranked": True}
        )


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


class SourceChoicesTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_real_scraper_source_slugs_are_valid_on_patch(self):
        sources = [
            "indeed",
            "linkedin",
            "japan_dev",
            "tokyo_dev",
            "daijob",
            "gaijinpot",
            "careercross",
            "green",
            "wantedly",
            "japan-dev",
            "tokyodev",
            "custom",
        ]
        for source in sources:
            with self.subTest(source=source):
                job = Job.objects.create(
                    title=f"{source} Engineer",
                    company="Acme",
                    url=f"https://example.com/{source}",
                    url_hash=f"hash-{source}",
                    source=source,
                    is_formatted=False,
                )
                resp = self.client.patch(
                    reverse("job-detail", args=[job.id]),
                    data={
                        "source": source,
                        "description": "formatted",
                        "is_formatted": True,
                    },
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200, resp.content)

    def test_jobs_list_has_stable_default_order(self):
        older = Job.objects.create(
            title="Older",
            company="Acme",
            url="https://example.com/older",
            url_hash="hash-older",
        )
        newer = Job.objects.create(
            title="Newer",
            company="Acme",
            url="https://example.com/newer",
            url_hash="hash-newer",
        )

        resp = self.client.get(reverse("job-list"))

        self.assertEqual(resp.status_code, 200)
        ids = [item["id"] for item in resp.json()["results"]]
        self.assertEqual(ids[:2], [newer.id, older.id])


class FormattingTaskPersistenceTests(TestCase):
    @patch("tasks.formatting._release_processing_state")
    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_permanent_persist_failure_raises_and_releases_lock(
        self, mock_format_job, mock_persistence_cls, mock_release
    ):
        error = requests.HTTPError("400 Bad Request")
        error.response = MagicMock(
            status_code=400,
            text='{"source":["\\"wantedly\\" is not a valid choice."]}',
        )
        mock_persistence_cls.return_value.update_job.side_effect = error
        mock_format_job.return_value = {
            "title": "Engineer",
            "company": "Acme",
            "url": "https://example.com/job",
            "source": "wantedly",
            "description": "formatted",
        }

        from tasks.formatting import format_and_persist_job

        with self.assertRaises(requests.HTTPError):
            format_and_persist_job.run({
                "id": 123,
                "title": "Engineer",
                "company": "Acme",
                "url": "https://example.com/job",
                "source": "wantedly",
                "raw_data": {},
            })

        mock_release.assert_called_once_with(123, None)

    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_blank_required_llm_fields_fall_back_to_original_job_data(
        self, mock_format_job, mock_persistence_cls
    ):
        mock_format_job.return_value = {
            "title": "Formatted title",
            "company": "",
            "url": "",
            "source": "",
            "description": "formatted",
        }
        mock_persistence_cls.return_value.update_job.return_value = {"id": 123}

        from tasks.formatting import format_and_persist_job

        format_and_persist_job.run({
            "id": 123,
            "title": "Original title",
            "company": "Original Company",
            "url": "https://example.com/job",
            "source": "green",
            "raw_data": {"description": "raw"},
        })

        persisted = mock_persistence_cls.return_value.update_job.call_args.args[1]
        self.assertEqual(persisted["company"], "Original Company")
        self.assertEqual(persisted["url"], "https://example.com/job")
        self.assertEqual(persisted["source"], "green")


class RankingTaskPersistenceTests(TestCase):
    @patch("tasks.ranking._clear_processing_lock")
    def test_no_job_data_clears_processing_lock(self, mock_clear_lock):
        from tasks.ranking import rank_job_multi_profile

        result = rank_job_multi_profile.run(
            False,
            profiles=[{"id": "backend_platform_engineer"}],
            pipeline_run_id=None,
            job_id=123,
        )

        self.assertEqual(result["status"], "skipped")
        mock_clear_lock.assert_called_once_with(123)

    @patch("tasks.ranking.requests.post")
    def test_ranking_persist_failure_is_not_swallowed(self, mock_post):
        response = MagicMock(status_code=500, text="server error")
        response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_post.return_value = response

        from tasks.ranking import _persist_rankings

        with self.assertRaises(requests.HTTPError):
            _persist_rankings(123, [{
                "profile_id": "backend_platform_engineer",
                "match_tier": "A",
                "rank": 10,
                "jd_summary": "summary",
            }])


class PipelineBatchPersistenceTests(TestCase):
    def test_batch_save_failure_falls_back_per_job_and_recovers_job_map(self):
        from tasks.pipeline import _save_jobs_with_fallback

        persister = MagicMock()
        persister.save_jobs.side_effect = [
            requests.Timeout("bulk timed out after commit"),
            {"jobs": {"https://example.com/job-a": {"id": 1, "is_formatted": False}}},
            {"jobs": {"https://example.com/job-b": {"id": 2, "is_formatted": False}}},
        ]

        jobs_by_url = _save_jobs_with_fallback(persister, [
            {"url": "https://example.com/job-a", "title": "A"},
            {"url": "https://example.com/job-b", "title": "B"},
        ])

        self.assertEqual(set(jobs_by_url), {
            "https://example.com/job-a",
            "https://example.com/job-b",
        })
        self.assertEqual(persister.save_jobs.call_count, 3)

    def test_incomplete_batch_response_only_retries_missing_urls(self):
        from tasks.pipeline import _save_jobs_with_fallback

        persister = MagicMock()
        persister.save_jobs.side_effect = [
            {"jobs": {"https://example.com/job-a": {"id": 1, "is_formatted": False}}},
            {"jobs": {"https://example.com/job-b": {"id": 2, "is_formatted": False}}},
        ]

        jobs_by_url = _save_jobs_with_fallback(persister, [
            {"url": "https://example.com/job-a", "title": "A"},
            {"url": "https://example.com/job-b", "title": "B"},
        ])

        self.assertEqual(jobs_by_url["https://example.com/job-a"]["id"], 1)
        self.assertEqual(jobs_by_url["https://example.com/job-b"]["id"], 2)
        self.assertEqual(persister.save_jobs.call_args_list[1].args[0], [
            {"url": "https://example.com/job-b", "title": "B"}
        ])


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
        # jobs map must reflect the REAL DB is_formatted=True so the poller
        # can skip re-queuing without a follow-up GET (H1).
        from .parsers import normalize_url as _norm2
        jobs_map = resp.json().get("jobs", {})
        self.assertTrue(jobs_map.get(_norm2(url1), {}).get("is_formatted"),
                        "bulk_create must return is_formatted=True from DB, not from stub payload")

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

    def test_bulk_create_returns_job_map(self):
        """bulk_create response must include jobs dict keyed by normalized URL
        with id and is_formatted — lets the pipeline skip follow-up GETs (H1)."""
        resp = self.client.post(
            reverse("job-bulk-create"),
            data=[
                {"url": "https://co.example/map1", "title": "Eng A", "company": "Acme"},
                {"url": "https://co.example/map2", "title": "Eng B", "company": "Acme",
                 "is_formatted": True},
            ],
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (200, 201))
        data = resp.json()
        jobs = data.get("jobs", {})
        self.assertIn("https://co.example/map1", jobs, "jobs map missing url key")
        self.assertIn("https://co.example/map2", jobs, "jobs map missing url key")
        for norm_url in ("https://co.example/map1", "https://co.example/map2"):
            entry = jobs[norm_url]
            self.assertIn("id", entry)
            self.assertIsInstance(entry["id"], int)
            self.assertIn("is_formatted", entry)
        self.assertFalse(jobs["https://co.example/map1"]["is_formatted"])
        self.assertTrue(jobs["https://co.example/map2"]["is_formatted"])

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


class JobAppliedTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.other_user = User.objects.create_user(username="otheruser", password="password")
        self.client.force_login(self.user)

        self.job_applied = Job.objects.create(
            title="Applied Job",
            company="Company A",
            url="https://a.com",
            url_hash="hash_a",
            is_active=True,
        )
        self.ranking_applied = JobRanking.objects.create(
            job=self.job_applied,
            profile_id="test_profile",
            match_tier="S",
            rank=1,
        )

        self.job_not_applied = Job.objects.create(
            title="Not Applied Job",
            company="Company B",
            url="https://b.com",
            url_hash="hash_b",
            is_active=True,
        )
        self.ranking_not_applied = JobRanking.objects.create(
            job=self.job_not_applied,
            profile_id="test_profile",
            match_tier="S",
            rank=2,
        )

        JobApplicationStatus.objects.create(
            user=self.user,
            job=self.job_applied,
            is_applied=True,
        )
        JobApplicationStatus.objects.create(
            user=self.other_user,
            job=self.job_not_applied,
            is_applied=True,
        )

    def test_applied_filtering_true(self):
        url = reverse("browse")
        response = self.client.get(f"{url}?profile_id=test_profile&applied=true&date=all")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["job"]["id"], self.job_applied.id)

    def test_applied_filtering_false(self):
        url = reverse("browse")
        response = self.client.get(f"{url}?profile_id=test_profile&applied=false&date=all")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["job"]["id"], self.job_not_applied.id)

    def test_applied_filtering_all(self):
        url = reverse("browse")
        response = self.client.get(f"{url}?profile_id=test_profile&applied=&date=all")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 2)

    def test_applied_filtering_is_user_scoped(self):
        self.client.force_login(self.other_user)
        url = reverse("browse")
        response = self.client.get(f"{url}?profile_id=test_profile&applied=true&date=all")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["job"]["id"], self.job_not_applied.id)

    def test_patch_updates_only_current_user_application_status(self):
        url = reverse("job-detail", kwargs={"pk": self.job_not_applied.id})
        response = self.client.patch(
            url,
            data='{"is_applied": true}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_applied"])

        self.assertTrue(
            JobApplicationStatus.objects.filter(
                user=self.user,
                job=self.job_not_applied,
                is_applied=True,
            ).exists()
        )
        self.assertTrue(
            JobApplicationStatus.objects.filter(
                user=self.other_user,
                job=self.job_not_applied,
                is_applied=True,
            ).exists()
        )


class NormalizeUrlTests(TestCase):
    """normalize_url must preserve identity params and strip tracking params."""

    def _norm(self, url):
        from jobs.parsers import normalize_url
        return normalize_url(url)

    def test_indeed_jk_kept(self):
        url = "https://www.indeed.com/viewjob?jk=abc123&refnum=xyz&from=organic"
        self.assertEqual(self._norm(url), "https://www.indeed.com/viewjob?jk=abc123")

    def test_taleo_job_param_kept(self):
        url = "https://company.taleo.net/careersection/2/jobdetail.ftl?job=12345&lang=en"
        self.assertEqual(self._norm(url), "https://company.taleo.net/careersection/2/jobdetail.ftl?job=12345")

    def test_jobvite_j_param_kept(self):
        url = "https://hire.jobvite.com/Jobvite/job.aspx?j=abc123&s=LinkedIn"
        self.assertEqual(self._norm(url), "https://hire.jobvite.com/Jobvite/job.aspx?j=abc123")

    def test_linkedin_tracking_stripped(self):
        url = "https://www.linkedin.com/jobs/view/12345?refId=abc&trackingId=xyz"
        self.assertEqual(self._norm(url), "https://www.linkedin.com/jobs/view/12345")

    def test_trailing_slash_stripped(self):
        self.assertEqual(self._norm("https://example.com/jobs/123/"), "https://example.com/jobs/123")

    # (input, expected) — exercised against BOTH normalizers below.
    PARITY_CASES = [
        ("https://www.indeed.com/viewjob?jk=abc123&refnum=xyz&from=organic",
         "https://www.indeed.com/viewjob?jk=abc123"),
        ("https://jobs.indeed.com/viewjob?jk=sub42&utm=x",
         "https://jobs.indeed.com/viewjob?jk=sub42"),
        ("https://company.taleo.net/careersection/2/jobdetail.ftl?job=12345&lang=en",
         "https://company.taleo.net/careersection/2/jobdetail.ftl?job=12345"),
        ("https://hire.jobvite.com/Jobvite/job.aspx?j=abc123&s=LinkedIn",
         "https://hire.jobvite.com/Jobvite/job.aspx?j=abc123"),
        ("https://www.linkedin.com/jobs/view/12345?refId=abc&trackingId=xyz",
         "https://www.linkedin.com/jobs/view/12345"),
        ("https://example.com/jobs/123/", "https://example.com/jobs/123"),
        # Substring guard: a host merely *containing* an allowlisted domain must
        # NOT inherit its rule — jk here is a tracking param and gets stripped.
        ("https://notindeed.com/viewjob?jk=abc123", "https://notindeed.com/viewjob"),
    ]

    def test_parity_both_normalizers_identical(self):
        """persistence.normalize_url (Celery side) and jobs.parsers.normalize_url
        (Django side) must produce byte-identical output — #22 dedup depends on it."""
        from jobs.parsers import normalize_url as parsers_norm
        from persistence import normalize_url as persistence_norm
        for url, expected in self.PARITY_CASES:
            self.assertEqual(parsers_norm(url), expected, f"parsers: {url}")
            self.assertEqual(persistence_norm(url), expected, f"persistence: {url}")

    def test_substring_host_not_matched(self):
        self.assertEqual(self._norm("https://notindeed.com/viewjob?jk=abc123"),
                         "https://notindeed.com/viewjob")
