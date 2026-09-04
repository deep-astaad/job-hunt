"""Unit tests for required-language detection (persistence.py) and locations.py.

Issue #125 deleted the deterministic matching/ranking engine (matching.py) — the
LLM ranks every job now, with no deterministic tier assignment, skill/experience
scoring, or hard-fail pre-screen. This file used to be scratch/test_matching.py
and exercised that engine directly; the tests for compute_match, blend_with_llm,
canonical_skill/extract_job_skills, and prescreen_hard_fail are gone along with
it. What survives is detect_required_language, which moved to persistence.py
(it's pure data extraction used during formatting, not tier assignment — see
persistence.py's module comment), and the independent locations.py tests.

Run from repo root (no Django / Redis / network needed):
    uv run python -m unittest scratch.test_language_and_locations -v
    # or inside the worker container:
    docker compose exec celery-worker python -m unittest scratch.test_language_and_locations
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence import detect_required_language, detect_job_language
import locations


BACKEND_PROFILE = {
    "id": "backend_platform_engineer",
    "title": "Backend Platform Engineer",
    "experience_years": 2.5,
    "languages": ["English"],
    "target_locations": ["japan_tokyo", "remote_global"],
    "min_salary_yen": 4000000,
    "core_skills": ["Python", "Django", "FastAPI", "Celery", "PostgreSQL",
                    "Redis", "Docker", "AWS", "Kafka", "Linux"],
    "language_requirements": "English business level. No mandatory Japanese.",
}


class RequiredLanguageDetectionTests(unittest.TestCase):
    def test_required_language_japanese(self):
        lang, hard = detect_required_language(
            {"description": "Business level Japanese required. JLPT N2."})
        self.assertEqual(lang, "japanese")
        self.assertTrue(hard)

    def test_optional_japanese_not_hard(self):
        # "a plus" with no English-OK statement -> soft Japanese, not a hard gate.
        lang, hard = detect_required_language(
            {"description": "Japanese is a plus, nice to have. We use modern tooling."})
        self.assertEqual(lang, "japanese")
        self.assertFalse(hard)

    def test_english_ok_clears_japanese_gate(self):
        # An explicit English-OK statement means Japanese carries no weight at all,
        # even on a JP-labelled job (the old code hard-failed these false-negatively).
        lang, hard = detect_required_language(
            {"language": "JP",
             "description": "Japanese is a plus but not required. English OK."})
        self.assertFalse(hard)
        self.assertNotEqual(lang, "japanese")

    def test_jp_label_alone_is_not_a_hard_requirement(self):
        # A job labelled JP only because of incidental CJK (¥ salary, company name)
        # with an English description must not be hard-gated for Japanese.
        lang, hard = detect_required_language(
            {"language": "JP",
             "title": "Backend Engineer",
             "description": "We build Python/Django services on AWS. Salary 8,000,000 yen."})
        self.assertFalse(hard)


class DetectJobLanguageTests(unittest.TestCase):
    def test_detect_job_language_no_cjk_overtag(self):
        # A single kanji in the address must not tag an English role as JP.
        lang = detect_job_language({
            "title": "Backend Engineer",
            "description": "Build Python services. Office in 渋谷区.",
            "language": "EN",
        })
        self.assertEqual(lang, "EN")

    def test_detect_job_language_hard_jp_is_jp(self):
        lang = detect_job_language({
            "title": "エンジニア",
            "description": "Business level Japanese required, JLPT N2 minimum.",
        })
        self.assertEqual(lang, "JP")

    def test_detect_job_language_optional_jp_is_en(self):
        # Japanese as a nice-to-have must NOT be labeled JP (it's not required).
        lang = detect_job_language({
            "title": "Backend Engineer",
            "description": "English-speaking team. Japanese is a plus but not required.",
        })
        self.assertEqual(lang, "EN")


class LocationsConfigTests(unittest.TestCase):
    def test_active_ids_exist(self):
        for lid in locations.active_location_ids():
            self.assertIsNotNone(locations.get_location(lid))

    def test_profile_resolution(self):
        cfgs = locations.location_cfgs_for_profile(BACKEND_PROFILE)
        ids = {c["id"] for c in cfgs}
        self.assertEqual(ids, {"japan_tokyo", "remote_global"})

    def test_all_keyword(self):
        cfgs = locations.location_cfgs_for_profile({"target_locations": "all"})
        self.assertTrue(len(cfgs) >= 1)

    def test_region_for_text(self):
        region, country, city = locations.region_for_text("Remote role, team in Bangalore India")
        self.assertEqual(region, "india")
        self.assertEqual(country, "IN")


if __name__ == "__main__":
    unittest.main()
