"""Unit tests for the deterministic matching engine (matching.py) and locations.py.

Run from repo root (no Django / Redis / network needed):
    uv run python -m unittest scratch.test_matching -v
    # or inside the worker container:
    docker compose exec celery-worker python -m unittest scratch.test_matching
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matching
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

TOKYO_REMOTE = [locations.get_location("japan_tokyo"), locations.get_location("remote_global")]


class CanonicalSkillTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(matching.canonical_skill("JS"), "javascript")
        self.assertEqual(matching.canonical_skill("Postgres"), "postgresql")
        self.assertEqual(matching.canonical_skill("k8s"), "kubernetes")
        self.assertEqual(matching.canonical_skill("  Node.js "), "node.js")
        self.assertEqual(matching.canonical_skill("Golang"), "go")

    def test_extract_from_text(self):
        job = {"title": "Backend Engineer",
               "description": "We use Python, Django and PostgreSQL on AWS with Docker."}
        skills = matching.extract_job_skills(job)
        for expected in {"python", "django", "postgresql", "aws", "docker"}:
            self.assertIn(expected, skills)


class ExperienceLanguageParsingTests(unittest.TestCase):
    def test_required_years(self):
        self.assertEqual(matching.parse_required_years("3+ years"), 3)
        self.assertEqual(matching.parse_required_years("minimum 5 years experience"), 5)
        self.assertEqual(matching.parse_required_years("2-4 yrs"), 2)
        self.assertIsNone(matching.parse_required_years(""))

    def test_required_language_japanese(self):
        lang, hard = matching.detect_required_language(
            {"description": "Business level Japanese required. JLPT N2."})
        self.assertEqual(lang, "japanese")
        self.assertTrue(hard)

    def test_optional_japanese_not_hard(self):
        # "a plus" with no English-OK statement -> soft Japanese, not a hard gate.
        lang, hard = matching.detect_required_language(
            {"description": "Japanese is a plus, nice to have. We use modern tooling."})
        self.assertEqual(lang, "japanese")
        self.assertFalse(hard)

    def test_english_ok_clears_japanese_gate(self):
        # An explicit English-OK statement means Japanese carries no weight at all,
        # even on a JP-labelled job (the old code hard-failed these false-negatively).
        lang, hard = matching.detect_required_language(
            {"language": "JP",
             "description": "Japanese is a plus but not required. English OK."})
        self.assertFalse(hard)
        self.assertNotEqual(lang, "japanese")

    def test_jp_label_alone_is_not_a_hard_requirement(self):
        # A job labelled JP only because of incidental CJK (¥ salary, company name)
        # with an English description must not be hard-gated for Japanese.
        lang, hard = matching.detect_required_language(
            {"language": "JP",
             "title": "Backend Engineer",
             "description": "We build Python/Django services on AWS. Salary 8,000,000 yen."})
        self.assertFalse(hard)

    def test_candidate_languages(self):
        langs = matching.candidate_languages(BACKEND_PROFILE)
        self.assertIn("english", langs)
        self.assertNotIn("japanese", langs)

    def test_detect_job_language_no_cjk_overtag(self):
        # A single kanji in the address must not tag an English role as JP.
        from persistence import detect_job_language
        lang = detect_job_language({
            "title": "Backend Engineer",
            "description": "Build Python services. Office in 渋谷区.",
            "language": "EN",
        })
        self.assertEqual(lang, "EN")

    def test_detect_job_language_hard_jp_is_jp(self):
        from persistence import detect_job_language
        lang = detect_job_language({
            "title": "エンジニア",
            "description": "Business level Japanese required, JLPT N2 minimum.",
        })
        self.assertEqual(lang, "JP")


class ComputeMatchTests(unittest.TestCase):
    def test_strong_match_is_high_tier(self):
        job = {
            "title": "Backend Engineer (Python)",
            "company": "GlobalSaaS",
            "description": "Build scalable Python/Django APIs with Celery, PostgreSQL, Redis, Docker on AWS. English-speaking international team in Tokyo.",
            "tech_stack": ["Python", "Django", "Celery", "PostgreSQL", "AWS"],
            "experience_required": "2 years",
            "language": "EN",
            "location": "Tokyo, Japan",
            "salary_yen": 7000000,
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertFalse(res["hard_fail"])
        self.assertIn(res["tier"], ("S", "A"))
        self.assertGreaterEqual(res["score"], 64)
        self.assertIn("python", res["signals"]["matched_skills"])

    def test_japanese_required_hard_fails(self):
        job = {
            "title": "Backend Engineer",
            "description": "Python and Django role. Business level Japanese (JLPT N2) is required.",
            "tech_stack": ["Python", "Django"],
            "experience_required": "2 years",
            "language": "JP",
            "location": "Tokyo, Japan",
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertTrue(res["hard_fail"])
        self.assertEqual(res["tier"], "F")
        self.assertIn("japanese", res["hard_fail_reason"])

    def test_senior_role_hard_fails(self):
        job = {
            "title": "Senior Staff Backend Engineer",
            "description": "Lead architecture for our Python platform.",
            "tech_stack": ["Python", "Django"],
            "experience_required": "8 years",
            "language": "EN",
            "location": "Remote",
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertTrue(res["hard_fail"])
        self.assertEqual(res["tier"], "F")

    def test_internship_hard_fails(self):
        job = {"title": "Software Engineering Intern", "description": "Python internship.",
               "tech_stack": ["Python"], "language": "EN", "location": "Tokyo"}
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertTrue(res["hard_fail"])

    def test_remote_job_matches_remote_target(self):
        job = {
            "title": "Backend Engineer",
            "description": "Fully remote Python/Django role, work from anywhere.",
            "tech_stack": ["Python", "Django", "PostgreSQL"],
            "experience_required": "2 years", "language": "EN", "location": "Remote",
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertEqual(res["signals"]["location"], 1.0)
        self.assertFalse(res["hard_fail"])

    def test_out_of_region_is_capped(self):
        job = {
            "title": "Backend Engineer",
            "description": "Python/Django role based in São Paulo, Brazil. On-site only.",
            "tech_stack": ["Python", "Django", "PostgreSQL", "AWS"],
            "experience_required": "2 years", "language": "EN",
            "location": "São Paulo, Brazil",
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        # Good skills but wrong location -> capped, never S/A.
        self.assertIn(res["tier"], ("C", "F"))

    def test_weak_skill_match_low_tier(self):
        job = {
            "title": "Frontend Engineer",
            "description": "Build UIs with React, Vue, CSS and design systems.",
            "tech_stack": ["React", "Vue", "CSS", "Figma"],
            "experience_required": "2 years", "language": "EN", "location": "Tokyo",
        }
        res = matching.compute_match(BACKEND_PROFILE, job, TOKYO_REMOTE)
        self.assertIn(res["tier"], ("B", "C", "F"))


class BlendTests(unittest.TestCase):
    def test_hard_fail_overrides_llm(self):
        det = {"score": 80, "tier": "F", "hard_fail": True,
               "hard_fail_reason": "requires japanese", "signals": {}}
        out = matching.blend_with_llm(det, "S")
        self.assertEqual(out["final_tier"], "F")

    def test_blend_pulls_toward_average(self):
        det = {"score": 70, "tier": "A", "hard_fail": False,
               "hard_fail_reason": None, "signals": {}}
        out = matching.blend_with_llm(det, "C")  # llm=38
        # 0.6*70 + 0.4*38 = 57.2 -> B
        self.assertEqual(out["final_tier"], "B")
        self.assertAlmostEqual(out["final_score"], 57.2, places=1)

    def test_no_llm_keeps_deterministic(self):
        det = {"score": 75, "tier": "A", "hard_fail": False,
               "hard_fail_reason": None, "signals": {}}
        out = matching.blend_with_llm(det, None)
        self.assertEqual(out["final_score"], 75)


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
