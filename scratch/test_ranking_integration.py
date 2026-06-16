"""Integration test for tasks.ranking._apply_matching_engine (LLM + deterministic blend).

Sets dummy provider env so importing celery_app/config doesn't bail. No network.

    APP_MODE=celery-worker APIFY_API_TOKEN=x OPENAI_API_KEY=x \
        uv run python -m unittest scratch.test_ranking_integration -v
"""
import os
import sys
import unittest

os.environ.setdefault("APP_MODE", "celery-worker")
os.environ.setdefault("APIFY_API_TOKEN", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import tasks.ranking as ranking

PROFILES = json.load(open(os.path.join(os.path.dirname(__file__), "..", "user-profiles.json")))


class ApplyMatchingEngineTests(unittest.TestCase):
    def _job(self, **over):
        base = {
            "id": 1, "title": "Backend Engineer (Python)", "company": "GlobalSaaS",
            "full_description": "Build scalable Python/Django APIs with Celery, "
                                "PostgreSQL, Redis on AWS. English-speaking team in Tokyo. 2 years.",
            "description": "Python/Django backend role",
            "tech_stack": ["Python", "Django", "Celery", "PostgreSQL", "AWS"],
            "experience_required": "2 years", "language": "EN",
            "location": "Tokyo, Japan", "salary_yen": 7000000,
        }
        base.update(over)
        return base

    def test_every_profile_gets_a_ranking(self):
        llm = [{"profile_id": "backend_platform_engineer", "match_tier": "A", "jd_summary": "x"}]
        out = ranking._apply_matching_engine(llm, self._job(), PROFILES)
        self.assertEqual(len(out), len(PROFILES))
        for r in out:
            self.assertIn(r["match_tier"], list("SABCF"))
            self.assertIsInstance(r["match_score"], int)
            self.assertIn("signals", r)
            self.assertEqual(r["rank"], max(0, 100 - r["match_score"]))

    def test_strong_backend_match_is_top_tier(self):
        llm = [{"profile_id": "backend_platform_engineer", "match_tier": "A", "jd_summary": "x"}]
        out = ranking._apply_matching_engine(llm, self._job(), PROFILES)
        backend = next(r for r in out if r["profile_id"] == "backend_platform_engineer")
        self.assertIn(backend["match_tier"], ("S", "A"))
        self.assertGreaterEqual(backend["match_score"], 64)

    def test_japanese_required_forces_f(self):
        job = self._job(
            language="JP",
            full_description="Python role. Business level Japanese (JLPT N2) required.",
        )
        llm = [{"profile_id": "backend_platform_engineer", "match_tier": "S", "jd_summary": "x"}]
        out = ranking._apply_matching_engine(llm, job, PROFILES)
        backend = next(r for r in out if r["profile_id"] == "backend_platform_engineer")
        self.assertEqual(backend["match_tier"], "F")
        self.assertEqual(backend["llm_tier"], "S")  # raw LLM tier preserved


if __name__ == "__main__":
    unittest.main()
