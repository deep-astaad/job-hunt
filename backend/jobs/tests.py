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

    @patch("tasks.pipeline._load_profiles_for_ranking")
    @patch("celery.chain")
    @patch("tasks.ranking.rank_job_multi_profile.delay")
    def test_process_unprocessed_jobs_task(self, mock_rank_delay, mock_chain, mock_load_profiles):
        mock_load_profiles.return_value = [{"id": "profile_1"}]
        
        from tasks.pipeline import process_unprocessed_jobs_task
        
        result = process_unprocessed_jobs_task()
        
        self.assertEqual(result.get("unformatted_processed"), 1)
        self.assertEqual(result.get("unranked_processed"), 1)
        
        # Verify formatting + ranking chain was triggered for unformatted job
        mock_chain.assert_called_once()
        
        # Verify rank task was called directly for unranked job
        mock_rank_delay.assert_called_once()


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
        )
        self.job2 = Job.objects.create(
            title="Engineer B",
            company="Company B",
            url="https://b.com",
            url_hash="hashb",
            is_formatted=True,
            is_ranked=False,
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

    def test_api_stats(self):
        url = reverse("job-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_jobs"], 2)
        self.assertEqual(data["formatted_jobs"], 2)
        self.assertEqual(data["ranked_jobs"], 1)


