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


class ProfileImmutabilityTests(unittest.TestCase):
    """Regression tests for H5: shared profile dicts must not be mutated by ranking tasks."""

    def _job(self):
        return {
            "id": 99, "title": "Backend Engineer (Python)", "company": "Acme",
            "full_description": "Python/Django role. 2 years exp. English OK. Tokyo.",
            "description": "Python/Django backend role",
            "tech_stack": ["Python", "Django"],
            "experience_required": "2 years", "language": "EN", "location": "Tokyo, Japan",
        }

    def test_experience_years_float_preserved_after_ranking(self):
        import copy
        profiles_before = copy.deepcopy(PROFILES)
        llm = [{"profile_id": p["id"], "match_tier": "A", "jd_summary": "x"} for p in PROFILES]
        ranking._apply_matching_engine(llm, self._job(), PROFILES)
        for orig, after in zip(profiles_before, PROFILES):
            self.assertEqual(
                orig.get("experience_years"),
                after.get("experience_years"),
                f"Profile {orig['id']} experience_years was mutated from "
                f"{orig.get('experience_years')} to {after.get('experience_years')}",
            )

    def test_experience_years_float_used_in_gate(self):
        # Profile with 2.5y experience: a job requiring "5.5 years" is the exact boundary
        # where int truncation produces the wrong result.
        # float 2.5: 5.5 > 2.5+3=5.5 → False (no hard fail — borderline stretch, OK)
        # int   2:   5.5 > 2+3=5    → True  (hard fail — wrong, truncation error)
        backend = next(p for p in PROFILES if "backend" in p.get("id", ""))
        self.assertEqual(backend.get("experience_years"), 2.5,
                         "test requires the backend profile to have experience_years=2.5")
        job = self._job()
        job["experience_required"] = "5.5 years"
        result = ranking._apply_matching_engine(
            [{"profile_id": backend["id"], "match_tier": "B", "jd_summary": "x"}],
            job, [backend]
        )
        match = result[0]
        self.assertNotEqual(
            match["match_tier"], "F",
            "Experience gate hard-failed a 2.5y candidate at 5.5y required — "
            "suggests truncated int (2) was used: 5.5 > 2+3=5 is True but 5.5 > 2.5+3=5.5 is False"
        )


if __name__ == "__main__":
    unittest.main()
