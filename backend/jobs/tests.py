import json
import os

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


class DispatchJobTests(TestCase):
    """Issue #125: the pre-screen path (LLM-free F tiers) is deleted outright.

    _persist_prescreen_f and _dispatch_or_prescreen no longer exist, and the
    replacement _dispatch_job unconditionally dispatches the format->rank chain
    — there is no longer any code path that can assign a job a tier without an
    LLM call.
    """

    def test_prescreen_functions_are_gone(self):
        import tasks.pipeline as pipeline_mod

        self.assertFalse(hasattr(pipeline_mod, "_persist_prescreen_f"))
        self.assertFalse(hasattr(pipeline_mod, "_dispatch_or_prescreen"))

    @patch("tasks.pipeline.chain")
    def test_dispatch_job_always_dispatches_the_format_rank_chain(self, mock_chain):
        from tasks.pipeline import _dispatch_job

        r = MagicMock()
        job_data = {"id": 999, "title": "Backend Engineer", "raw_data": {}}

        _dispatch_job(job_data, [{"id": "p1"}], r, "run-1")

        # No matter what the job looks like, the only outcome is: dispatched.
        mock_chain.assert_called_once()
        mock_chain.return_value.apply_async.assert_called_once()
        r.sadd.assert_called_once_with("pipeline:run-1:in_flight", 999)


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
        # A second unformatted job so unformatted_count (2) != unranked_count (1)
        # -- deliberately asymmetric so a formatting_depth/ranking_depth swap bug
        # would flip one queue's skip decision and fail this test (see the
        # dedicated swap-check assertions below).
        Job.objects.create(
            title="Second Unformatted Engineer",
            company="Company D",
            url="https://comp-d.com/job",
            url_hash="hash_d",
            is_formatted=False,
        )

        mock_load_profiles.return_value = [{"id": "profile_1"}]
        fake_redis = mock_redis_from_url.return_value
        # Isolate from any real Redis: the per-job dedup lock always "acquires",
        # and no job currently holds a lock.
        fake_redis.set.return_value = True
        fake_redis.exists.return_value = False
        # Distinct, sub-saturating depths per queue: formatting=1 < 2 unformatted,
        # ranking=0 < 1 unranked -- both gates must stay open.
        fake_redis.llen.side_effect = {"formatting": 1, "ranking": 0}.get

        from tasks.pipeline import process_unprocessed_jobs_task

        result = process_unprocessed_jobs_task()

        self.assertEqual(result.get("unformatted_processed"), 2)
        self.assertEqual(result.get("unranked_processed"), 1)
        self.assertFalse(result.get("unformatted_dispatch_skipped"))
        self.assertFalse(result.get("unranked_dispatch_skipped"))
        self.assertEqual(result.get("unformatted_dispatched"), 2)
        self.assertEqual(result.get("unranked_dispatched"), 1)
        self.assertEqual(result.get("unformatted_locks_refreshed"), 0)
        self.assertEqual(result.get("unranked_locks_refreshed"), 0)

        # Verify formatting + ranking chain was triggered for each unformatted job
        self.assertEqual(mock_chain.call_count, 2)

        # Verify rank task was called directly for the unranked job
        mock_rank_apply_async.assert_called_once()

        # Each queue's own depth must actually have been consulted (this is what
        # would catch a formatting_depth/ranking_depth swap: with these chosen
        # values, swapping them would incorrectly close the unranked gate, since
        # formatting's depth (1) >= unranked's count (1)).
        fake_redis.llen.assert_any_call("formatting")
        fake_redis.llen.assert_any_call("ranking")

    @patch("redis.Redis.from_url")
    @patch("tasks.pipeline._load_profiles_for_ranking")
    @patch("celery.chain")
    @patch("tasks.ranking.rank_job_multi_profile.apply_async")
    def test_process_unprocessed_jobs_task_heartbeats_instead_of_redispatching(
        self, mock_rank_apply_async, mock_chain, mock_load_profiles, mock_redis_from_url
    ):
        """Issue #124 fix-round-2 regression (reopen-boundary defect): a job that
        already holds its processing lock must have that lock refreshed, never a
        second message enqueued for it -- even while the coarse queue-depth gate
        is closed. A job with no lock at all must also not be dispatched while
        the gate is closed, and must NOT have a lock created for it either (that
        would silently stall it until the phantom lock itself expired)."""
        # A second, lockless unformatted job -- must stay untouched while the
        # gate is closed (not dispatched, and no lock created for it either).
        Job.objects.create(
            title="Fresh Unformatted (no lock yet)",
            company="Company D",
            url="https://comp-d.com/job",
            url_hash="hash_d",
            is_formatted=False,
        )

        mock_load_profiles.return_value = [{"id": "profile_1"}]
        fake_redis = mock_redis_from_url.return_value

        locked_keys = {
            f"job_processing_lock:{self.unformatted_job.id}",
            f"job_processing_lock:{self.unranked_job.id}",
        }
        fake_redis.exists.side_effect = lambda key: key in locked_keys
        # Distinct depths/counts per queue: formatting=10 >= 2 unformatted jobs,
        # ranking=3 >= 1 unranked job -- both gates closed, but for different
        # (asymmetric) reasons, so a depth/count swap would not coincidentally
        # produce the same result.
        fake_redis.llen.side_effect = {"formatting": 10, "ranking": 3}.get

        from tasks.pipeline import process_unprocessed_jobs_task

        result = process_unprocessed_jobs_task()

        self.assertTrue(result.get("unformatted_dispatch_skipped"))
        self.assertTrue(result.get("unranked_dispatch_skipped"))
        self.assertEqual(result.get("unformatted_dispatched"), 0)
        self.assertEqual(result.get("unranked_dispatched"), 0)
        self.assertEqual(result.get("unformatted_locks_refreshed"), 1)
        self.assertEqual(result.get("unranked_locks_refreshed"), 1)

        # Nothing was (re-)dispatched for either the already-locked jobs or the
        # lockless-but-gated fresh job.
        mock_chain.assert_not_called()
        mock_rank_apply_async.assert_not_called()

        # The already-locked jobs' TTLs were heartbeated back to the full window...
        fake_redis.expire.assert_any_call(
            f"job_processing_lock:{self.unformatted_job.id}", 3600
        )
        fake_redis.expire.assert_any_call(
            f"job_processing_lock:{self.unranked_job.id}", 3600
        )

        # ...and no lock was ever created for the lockless fresh job while the
        # gate was closed (a stray lock there would stall it, not protect it).
        fake_redis.set.assert_not_called()

        fake_redis.llen.assert_any_call("formatting")
        fake_redis.llen.assert_any_call("ranking")


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

    # --- Issue #125d fix 1: LLM-error branch releases the lock on exhaustion ---

    def test_retry_or_release_releases_lock_and_reraises_original_exception_on_exhaustion(self):
        """Unit-level proof for _retry_or_release itself: once retries are
        exhausted, it must release the processing lock and re-raise the
        ORIGINAL exception (not a Celery Retry-wrapped one) - never call
        self.retry() in that case."""
        import openai

        from tasks.formatting import _retry_or_release

        fake_self = MagicMock()
        fake_self.request.retries = 5
        fake_self.max_retries = 5
        exc = openai.RateLimitError("rate limited", response=MagicMock(), body=None)

        with patch("tasks.formatting._release_processing_state") as mock_release:
            with self.assertRaises(openai.RateLimitError):
                _retry_or_release(fake_self, exc, job_id=456, pipeline_run_id=None)

        mock_release.assert_called_once_with(456, None)
        fake_self.retry.assert_not_called()

    def test_retry_or_release_keeps_backoff_and_does_not_release_when_not_exhausted(self):
        """Non-exhausted case must still call self.retry with the same
        backoff formula (30 * 2**retries) the old direct `self.retry(...)`
        call used, and must NOT release the lock (that would let a second
        dispatch race the still-pending retry)."""
        from tasks.formatting import _retry_or_release

        fake_self = MagicMock()
        fake_self.request.retries = 2
        fake_self.max_retries = 5
        fake_self.retry.side_effect = Exception("celery would raise Retry here")
        exc = ValueError("transient")

        with patch("tasks.formatting._release_processing_state") as mock_release:
            with self.assertRaises(Exception):
                _retry_or_release(fake_self, exc, job_id=789, pipeline_run_id=None)

        fake_self.retry.assert_called_once_with(exc=exc, countdown=30 * (2 ** 2))
        mock_release.assert_not_called()

    @patch("tasks.formatting._retry_or_release")
    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_llm_rate_limit_routes_through_retry_or_release_not_raw_retry(
        self, mock_format_job, mock_persistence_cls, mock_retry_or_release
    ):
        """format_and_persist_job's LLM-error branch must call
        _retry_or_release (which releases the lock on exhaustion) instead of
        `raise self.retry(...)` directly (which - per Celery's
        Task.retry - re-raises the original exception via
        raise_with_context, skipping _release_processing_state entirely and
        leaking job_processing_lock:<job_id> forever once the pipeline
        heartbeat (4029b56) starts refreshing it on every beat run)."""
        import openai

        exc = openai.RateLimitError("rate limited", response=MagicMock(), body=None)
        mock_format_job.side_effect = exc
        # Mimic _retry_or_release's real contract: it always raises.
        mock_retry_or_release.side_effect = exc

        from tasks.formatting import format_and_persist_job

        with patch.dict(os.environ, {"MOCK_LLM": "0"}):
            with self.assertRaises(openai.RateLimitError):
                format_and_persist_job.run({
                    "id": 789,
                    "title": "Engineer",
                    "company": "Acme",
                    "url": "https://example.com/job",
                    "source": "green",
                    "raw_data": {"description": "raw"},
                })

        mock_retry_or_release.assert_called_once()
        args = mock_retry_or_release.call_args.args
        self.assertIs(args[1], exc)
        self.assertEqual(args[2], 789)
        self.assertIsNone(args[3])

    # --- Issue #125d fix 2: LLMResponseError retries instead of fabricating,
    # and a content-free fallback is never marked is_formatted=True ---

    @patch("tasks.formatting._fallback_from_raw")
    @patch("tasks.formatting._retry_or_release")
    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_llm_response_error_retries_instead_of_fabricating_fallback(
        self, mock_format_job, mock_persistence_cls, mock_retry_or_release, mock_fallback
    ):
        """LLMResponseError (OpenRouter's error-shaped HTTP 200 for rate
        limiting / free-tier throttling) must land in the retryable tuple,
        not the bare `except Exception` fallback path - otherwise it
        produces a content-free job the ranker can only honestly score F."""
        from llm import LLMResponseError

        exc = LLMResponseError("provider returned no choices")
        mock_format_job.side_effect = exc
        mock_retry_or_release.side_effect = exc

        from tasks.formatting import format_and_persist_job

        with patch.dict(os.environ, {"MOCK_LLM": "0"}):
            with self.assertRaises(LLMResponseError):
                format_and_persist_job.run({
                    "id": 790,
                    "title": "Engineer",
                    "company": "Acme",
                    "url": "https://example.com/job",
                    "source": "green",
                    "raw_data": {"description": "raw"},
                })

        mock_retry_or_release.assert_called_once()
        mock_fallback.assert_not_called()

    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_content_free_fallback_is_not_marked_formatted(
        self, mock_format_job, mock_persistence_cls
    ):
        """A fallback that produces no usable description/full_description
        (the normal case for a pipeline scraper stub, whose description and
        full_description are always "" - the real text lives only in
        raw_data) must NOT be marked is_formatted=True. Freezing that row as
        "done" is exactly the bug: the ranker then honestly scores an empty
        JD as F and the job is never reformatted or reranked again."""
        mock_format_job.side_effect = Exception("unexpected formatter failure")
        mock_persistence_cls.return_value.update_job.return_value = {"id": 321}

        from tasks.formatting import format_and_persist_job

        format_and_persist_job.run({
            "id": 321,
            "title": "Engineer",
            "company": "Acme",
            "url": "https://example.com/job",
            "source": "green",
            "description": "",
            "full_description": "",
            "raw_data": {"foo": "bar"},
        })

        persisted = mock_persistence_cls.return_value.update_job.call_args.args[1]
        self.assertFalse(persisted["is_formatted"])

    @patch("tasks.formatting.DjangoPersistence")
    @patch("tasks.formatting._formatter.format_job")
    def test_fallback_with_real_content_is_still_marked_formatted(
        self, mock_format_job, mock_persistence_cls
    ):
        """Honesty cuts both ways: if the fallback actually has real content
        to fall back on, it should still be marked formatted rather than
        needlessly stuck in the unformatted backlog forever."""
        mock_format_job.side_effect = Exception("unexpected formatter failure")
        mock_persistence_cls.return_value.update_job.return_value = {"id": 322}

        from tasks.formatting import format_and_persist_job

        format_and_persist_job.run({
            "id": 322,
            "title": "Engineer",
            "company": "Acme",
            "url": "https://example.com/job",
            "source": "green",
            "description": "Some real description text",
            "full_description": "",
            "raw_data": {},
        })

        persisted = mock_persistence_cls.return_value.update_job.call_args.args[1]
        self.assertTrue(persisted["is_formatted"])


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


class RankingsFromLlmTests(TestCase):
    """Issue #125: _rankings_from_llm (formerly _apply_matching_engine) is a thin
    mapper now — no deterministic engine, LLM tier is authoritative."""

    def test_llm_tier_is_authoritative_and_deterministic_fields_are_null(self):
        from tasks.ranking import _rankings_from_llm, TIER_SCORE

        llm_rankings = [
            {"profile_id": "p1", "match_tier": "S", "jd_summary": "great fit"},
        ]
        out = _rankings_from_llm(llm_rankings, [{"id": "p1"}])

        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(r["match_tier"], "S")
        self.assertEqual(r["llm_tier"], "S")
        self.assertIsNone(r["deterministic_tier"])
        self.assertIsNone(r["signals"])
        self.assertEqual(r["match_score"], TIER_SCORE["S"])
        self.assertEqual(r["rank"], 100 - TIER_SCORE["S"])

    def test_missing_llm_ranking_for_profile_raises(self):
        # Issue #125 F-6: this used to assert the fabrication bug itself --
        # a profile the LLM never returned a row for silently became "C".
        # That's exactly the silent-fabrication behaviour issue #125 exists
        # to eliminate; it must now raise instead of persisting a tier the
        # LLM never gave.
        from llm import LLMResponseError
        from tasks.ranking import _rankings_from_llm

        with self.assertRaises(LLMResponseError):
            _rankings_from_llm(
                [{"profile_id": "p2", "match_tier": "B", "jd_summary": "x", "match_score_raw": 50}],
                [{"id": "p1"}, {"id": "p2"}],
            )

    def test_garbled_match_tier_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _rankings_from_llm

        with self.assertRaises(LLMResponseError):
            _rankings_from_llm(
                [{"profile_id": "p1", "match_tier": "not-a-tier", "jd_summary": "x", "match_score_raw": None}],
                [{"id": "p1"}],
            )

    def test_blank_match_tier_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _rankings_from_llm

        with self.assertRaises(LLMResponseError):
            _rankings_from_llm(
                [{"profile_id": "p1", "match_tier": "", "jd_summary": "x", "match_score_raw": None}],
                [{"id": "p1"}],
            )

    def test_absent_match_tier_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _rankings_from_llm

        with self.assertRaises(LLMResponseError):
            _rankings_from_llm(
                [{"profile_id": "p1", "jd_summary": "x", "match_score_raw": None}],
                [{"id": "p1"}],
            )

    def test_duplicate_profile_id_rows_last_row_wins(self):
        # Documents current behaviour rather than asserting it's ideal:
        # _rankings_from_llm keys rows by profile_id into a dict, so a
        # duplicate silently overwrites the earlier row for that profile
        # instead of raising or merging. Exactly one ranking is still
        # produced per requested profile either way -- no profile is ever
        # left without a tier or given two.
        from tasks.ranking import _rankings_from_llm

        llm_rankings = [
            {"profile_id": "p1", "match_tier": "F", "jd_summary": "first", "match_score_raw": 5},
            {"profile_id": "p1", "match_tier": "S", "jd_summary": "second", "match_score_raw": 90},
        ]
        out = _rankings_from_llm(llm_rankings, [{"id": "p1"}])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["match_tier"], "S")
        self.assertEqual(out[0]["jd_summary"], "second")


class ParseRankingsJsonTests(TestCase):
    """Issue #125 F-6: the acceptance test only ever exercised well-formed LLM
    responses. These malformed-response shapes were never tested even though
    _parse_rankings_json is the first line of defence against re-introducing
    the silent-fabrication bug -- every one of them must raise
    LLMResponseError, never return an empty/partial ranking list."""

    PROFILES = [{"id": "p1"}, {"id": "p2"}]

    def test_unparseable_text_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        with self.assertRaises(LLMResponseError):
            _parse_rankings_json("not json at all {{{", self.PROFILES)

    def test_truncated_fenced_json_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        truncated = '```json\n{"rankings": [{"profile_id": "p1", "match_tier": "A"'
        with self.assertRaises(LLMResponseError):
            _parse_rankings_json(truncated, self.PROFILES)

    def test_empty_rankings_array_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        with self.assertRaises(LLMResponseError):
            _parse_rankings_json(json.dumps({"rankings": []}), self.PROFILES)

    def test_rankings_as_object_instead_of_array_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        with self.assertRaises(LLMResponseError):
            _parse_rankings_json(json.dumps({"rankings": {}}), self.PROFILES)

    def test_prose_prefixed_json_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        body = json.dumps({"rankings": [{"profile_id": "p1", "match_tier": "A"}]})
        with self.assertRaises(LLMResponseError):
            _parse_rankings_json("Here is the ranking you asked for:\n" + body, self.PROFILES)

    def test_none_raises(self):
        from llm import LLMResponseError
        from tasks.ranking import _parse_rankings_json

        with self.assertRaises(LLMResponseError):
            _parse_rankings_json(None, self.PROFILES)


class ResolveMatchScoreTests(TestCase):
    """Issue #125 F-6 / F-2: _resolve_match_score is the enforcement point for
    tier/score consistency -- covers validation (valid/out-of-range/
    non-numeric/missing) and the F-2 band-clamping behaviour."""

    def test_valid_score_within_its_tier_band_is_returned_as_is(self):
        from tasks.ranking import _resolve_match_score

        self.assertEqual(_resolve_match_score(45, "B"), 45)

    def test_out_of_0_100_range_falls_back_to_tier_score(self):
        from tasks.ranking import TIER_SCORE, _resolve_match_score

        self.assertEqual(_resolve_match_score(150, "B"), TIER_SCORE["B"])
        self.assertEqual(_resolve_match_score(-5, "B"), TIER_SCORE["B"])

    def test_non_numeric_falls_back_to_tier_score(self):
        from tasks.ranking import TIER_SCORE, _resolve_match_score

        self.assertEqual(_resolve_match_score("not-a-number", "C"), TIER_SCORE["C"])
        self.assertEqual(_resolve_match_score([1, 2], "C"), TIER_SCORE["C"])

    def test_missing_falls_back_to_tier_score(self):
        from tasks.ranking import TIER_SCORE, _resolve_match_score

        self.assertEqual(_resolve_match_score(None, "F"), TIER_SCORE["F"])

    def test_bool_falls_back_to_tier_score(self):
        # bool is an int subclass in Python -- a literal True/False must not
        # be accepted as a real score.
        from tasks.ranking import TIER_SCORE, _resolve_match_score

        self.assertEqual(_resolve_match_score(True, "S"), TIER_SCORE["S"])

    def test_valid_score_outside_its_own_tier_band_is_clamped_into_band(self):
        # Issue #125 F-2: match_tier="F" with match_score=95 used to persist
        # verbatim, sorting that F job ahead of a real S job -- the tier is
        # authoritative, so an inconsistent-but-numeric score gets pulled
        # back into its own tier's documented band rather than trusted or
        # discarded.
        from tasks.ranking import TIER_SCORE_RANGE, _resolve_match_score

        f_lo, f_hi = TIER_SCORE_RANGE["F"]
        self.assertEqual(_resolve_match_score(95, "F"), f_hi)

        s_lo, s_hi = TIER_SCORE_RANGE["S"]
        self.assertEqual(_resolve_match_score(2, "S"), s_lo)


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
