"""
Offline ranking audit: runs the deterministic matching engine (feature branch)
against live jobs extracted from the DB, compares with existing LLM-only rankings,
and generates a markdown report saved to <repo>/ranking_audit_report.md.

Run from the repo root:
  cd /home/neovara/job-hunt-feature
  uv run python scratch/audit_rankings.py /tmp/jobs_audit_raw.json
"""
from __future__ import annotations

import json
import sys
import os
import collections
from pathlib import Path

# Add repo root so matching/locations are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from matching import compute_match, blend_with_llm, score_to_tier, TIER_ORDER
from locations import load_locations, location_cfgs_for_profile

# ── Load data ──────────────────────────────────────────────────────────────
jobs_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/jobs_audit_raw.json"
with open(jobs_file) as f:
    jobs = json.load(f)

profiles_file = Path(__file__).parent.parent / "user-profiles.json"
with open(profiles_file) as f:
    profiles = json.load(f)

profile_map = {p["id"]: p for p in profiles}

# Pre-load location configs
all_location_cfgs = load_locations()

print(f"Loaded {len(jobs)} jobs, {len(profiles)} profiles", file=sys.stderr)

# ── Per-job audit ──────────────────────────────────────────────────────────
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}  # lower = better

results_by_profile: dict[str, list[dict]] = collections.defaultdict(list)
mismatches = []  # big shifts
interesting = []  # hard-fail override cases
tier_delta_histogram: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))

for job in jobs:
    if not job["rankings"]:
        continue
    existing_by_profile = {r["profile_id"]: r for r in job["rankings"]}

    for pid, profile in profile_map.items():
        loc_cfgs = location_cfgs_for_profile(profile)
        det = compute_match(profile, job, loc_cfgs)
        # Existing ranking (may not exist)
        existing = existing_by_profile.get(pid)
        existing_tier = existing["match_tier"] if existing else None
        existing_llm_tier = existing.get("llm_tier") if existing else None
        # Blended result using existing LLM tier (or det tier if none)
        llm_tier = existing_llm_tier or det["tier"]
        blended = blend_with_llm(det, llm_tier)

        row = {
            "job_id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location", ""),
            "tech_stack": job.get("tech_stack", []),
            "profile_id": pid,
            "existing_tier": existing_tier,
            "existing_llm_tier": existing_llm_tier,
            "det_tier": det["tier"],
            "det_score": det["score"],
            "final_tier": blended["final_tier"],
            "final_score": blended["final_score"],
            "hard_fail": det.get("hard_fail", False),
            "hard_fail_reason": det.get("hard_fail_reason", ""),
            "signals": det.get("signals", {}),
        }
        results_by_profile[pid].append(row)

        # Detect significant mismatch: existing tier vs new final tier differ by >=2 ranks
        if existing_tier:
            old_rank = TIER_RANK.get(existing_tier, 4)
            new_rank = TIER_RANK.get(blended["final_tier"], 4)
            delta = new_rank - old_rank  # positive = downgraded, negative = upgraded
            tier_delta_histogram[pid][f"{existing_tier}->{blended['final_tier']}"] += 1
            if abs(delta) >= 2:
                mismatches.append(row)
            if det.get("hard_fail") and existing_tier in ("S", "A", "B"):
                interesting.append(row)

# ── Build report ───────────────────────────────────────────────────────────
lines = []
add = lines.append

add("# Ranking Audit Report")
add("")
add(f"**Jobs analysed:** {len(jobs)}  ")
add(f"**Profiles:** {len(profiles)}  ")
add(f"**Date:** 2026-06-15  ")
add("")
add("Engine: deterministic matching (feature/matching-locations branch) blended with existing LLM tiers from live DB.")
add("")

# ── Summary per profile ────────────────────────────────────────────────────
add("## 1. Tier distribution: existing vs new (per profile)")
add("")
for pid, rows in results_by_profile.items():
    profile = profile_map[pid]
    total = len(rows)
    ranked = sum(1 for r in rows if r["existing_tier"])
    old_dist = collections.Counter(r["existing_tier"] for r in rows if r["existing_tier"])
    new_dist = collections.Counter(r["final_tier"] for r in rows)
    add(f"### {profile['title']} (`{pid}`)")
    add(f"Ranked jobs: {ranked}/{total}")
    add("")
    add("| Tier | Old count | New count | Δ |")
    add("|------|-----------|-----------|---|")
    for t in TIER_ORDER:
        o = old_dist.get(t, 0)
        n = new_dist.get(t, 0)
        delta_str = f"+{n-o}" if n > o else str(n - o)
        add(f"| {t} | {o} | {n} | {delta_str} |")
    add("")

    add("**Tier transition matrix** (old→new, ranked jobs only):")
    add("")
    add("| Old\\New | " + " | ".join(TIER_ORDER) + " |")
    add("|---------|" + "---------|" * len(TIER_ORDER))
    for old_t in TIER_ORDER:
        cells = []
        for new_t in TIER_ORDER:
            count = sum(1 for r in rows if r["existing_tier"] == old_t and r["final_tier"] == new_t)
            cells.append(str(count) if count else ".")
        add(f"| {old_t} | " + " | ".join(cells) + " |")
    add("")

# ── Big movers ─────────────────────────────────────────────────────────────
add("## 2. Large tier shifts (≥2 tier steps)")
add("")
add(f"Total large shifts across all profiles: **{len(mismatches)}**")
add("")

upgrades = [r for r in mismatches if TIER_RANK[r["final_tier"]] < TIER_RANK[r["existing_tier"]]]
downgrades = [r for r in mismatches if TIER_RANK[r["final_tier"]] > TIER_RANK[r["existing_tier"]]]

add(f"- Upgraded (engine rates higher): {len(upgrades)}")
add(f"- Downgraded (engine rates lower): {len(downgrades)}")
add("")

def _job_row(r, kind):
    sigs = r["signals"]
    skill_s = f"{sigs.get('skill',0)*100:.0f}%"
    loc_s   = f"{sigs.get('location',0)*100:.0f}%"
    exp_s   = f"{sigs.get('experience',0)*100:.0f}%"
    stack_preview = ", ".join((r["tech_stack"] or [])[:5])
    reason = r["hard_fail_reason"] or f"skill={skill_s} loc={loc_s} exp={exp_s}"
    return (f"| {r['company']} | {r['title'][:40]} | {r['profile_id']} | "
            f"{r['existing_tier']}→**{r['final_tier']}** | {r['det_score']:.0f}/100 | "
            f"{reason} | {stack_preview[:40]} |")

if downgrades:
    add("### 2a. Downgrades (LLM over-rated)")
    add("")
    add("| Company | Title | Profile | Tier shift | Det score | Reason | Tech |")
    add("|---------|-------|---------|------------|-----------|--------|------|")
    for r in sorted(downgrades, key=lambda x: x["det_score"])[:40]:
        add(_job_row(r, "down"))
    add("")

if upgrades:
    add("### 2b. Upgrades (LLM under-rated)")
    add("")
    add("| Company | Title | Profile | Tier shift | Det score | Reason | Tech |")
    add("|---------|-------|---------|------------|-----------|--------|------|")
    for r in sorted(upgrades, key=lambda x: -x["det_score"])[:40]:
        add(_job_row(r, "up"))
    add("")

# ── Hard-fail overrides ────────────────────────────────────────────────────
add("## 3. Hard-fail gate overrides (engine→F despite LLM S/A/B)")
add("")
add(f"Total: **{len(interesting)}**")
add("")
if interesting:
    add("| Company | Title | Profile | Old tier | Hard-fail reason |")
    add("|---------|-------|---------|----------|-----------------|")
    reason_counter: collections.Counter = collections.Counter()
    for r in interesting:
        reason_counter[r["hard_fail_reason"]] += 1
        add(f"| {r['company']} | {r['title'][:45]} | {r['profile_id']} | {r['existing_tier']} | {r['hard_fail_reason']} |")
    add("")
    add("**Hard-fail reason breakdown:**")
    add("")
    for reason, cnt in reason_counter.most_common():
        add(f"- `{reason}`: {cnt}")
    add("")

# ── Signal analysis: where do jobs lose points? ───────────────────────────
add("## 4. Signal analysis (all ranked jobs, all profiles)")
add("")
add("Average score per signal component across ranked jobs:")
add("")
sig_keys = ["skill", "title", "experience", "language", "location"]
all_ranked = [r for rows in results_by_profile.values() for r in rows if r["existing_tier"]]
add("| Signal | Mean | P25 | Median | P75 |")
add("|--------|------|-----|--------|-----|")
import statistics
for key in sig_keys:
    vals = [r["signals"].get(key, 0) * 100 for r in all_ranked]
    if not vals:
        add(f"| {key} | n/a | n/a | n/a | n/a |")
        continue
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    p25 = vals_sorted[n // 4]
    p75 = vals_sorted[3 * n // 4]
    add(f"| {key} | {statistics.mean(vals):.1f} | {p25:.1f} | {statistics.median(vals):.1f} | {p75:.1f} |")
add("")

# ── Top unranked jobs the engine rates highly ─────────────────────────────
add("## 5. Unranked jobs the engine now rates A/S (missed by old LLM-only pipeline)")
add("")
for pid, rows in results_by_profile.items():
    missed = [r for r in rows if not r["existing_tier"] and r["final_tier"] in ("S", "A")]
    if not missed:
        continue
    add(f"### Profile: `{pid}` — {len(missed)} missed high-value jobs")
    add("")
    add("| Company | Title | Det score | Tech |")
    add("|---------|-------|-----------|------|")
    for r in sorted(missed, key=lambda x: -x["det_score"])[:20]:
        stack = ", ".join((r["tech_stack"] or [])[:5])
        add(f"| {r['company']} | {r['title'][:45]} | {r['det_score']:.0f} | {stack[:40]} |")
    add("")

# ── Common skill gaps ─────────────────────────────────────────────────────
add("## 6. Skill gap analysis (per profile, jobs rated B/C/F by engine)")
add("")
for pid, rows in results_by_profile.items():
    profile = profile_map[pid]
    weak_jobs = [r for r in rows if r["final_tier"] in ("B", "C", "F") and not r["hard_fail"]]
    if not weak_jobs:
        continue
    # Aggregate tech stacks of weak jobs to see what skills are commonly required
    tech_counter: collections.Counter = collections.Counter()
    for r in weak_jobs:
        for t in (r["tech_stack"] or []):
            tech_counter[t.lower()] += 1
    add(f"### `{pid}` — top tech in B/C/F jobs (skills the profile lacks coverage on)")
    add("")
    add("| Skill | Count |")
    add("|-------|-------|")
    for skill, cnt in tech_counter.most_common(15):
        add(f"| {skill} | {cnt} |")
    add("")

# ── Findings and recommendations ─────────────────────────────────────────
add("## 7. Key findings and recommended tuning")
add("")

# Auto-generate some findings
total_hard_fails = len(interesting)
pct_hard_fail = 100 * total_hard_fails / max(len(all_ranked), 1)
total_down = len(downgrades)
total_up = len(upgrades)

all_det_scores = [r["det_score"] for rows in results_by_profile.values() for r in rows if r["existing_tier"]]
mean_score = sum(all_det_scores) / max(len(all_det_scores), 1)

add(f"- **Hard-fail rate:** {total_hard_fails} jobs ({pct_hard_fail:.1f}% of ranked) are gated to F by the new engine despite the LLM giving them S/A/B. Verify these make sense.")
add(f"- **LLM vs engine disagreements ≥2 tiers:** {total_down} downgrades, {total_up} upgrades.")
add(f"- **Mean deterministic score:** {mean_score:.1f}/100 across ranked jobs.")
add("")

# Skill overlap issues
skill_scores = [r["signals"].get("skill", 0) * 100 for rows in results_by_profile.values() for r in rows if r["existing_tier"]]
if skill_scores:
    mean_skill = sum(skill_scores) / len(skill_scores)
    low_skill = sum(1 for s in skill_scores if s < 30)
    add(f"- **Skill signal:** mean {mean_skill:.1f}, {low_skill} jobs ({100*low_skill//max(len(skill_scores),1)}%) score <30 on skill overlap.")
    if mean_skill < 40:
        add("  - ⚠ Low mean skill score suggests the profile's `core_skills` list may not cover common JD vocabulary well. Consider expanding skill aliases in `matching.py` or adding more profile skills.")
    add("")

loc_scores = [r["signals"].get("location", 0) * 100 for rows in results_by_profile.values() for r in rows if r["existing_tier"]]
if loc_scores:
    zero_loc = sum(1 for s in loc_scores if s == 0)
    add(f"- **Location signal:** {zero_loc} jobs ({100*zero_loc//max(len(loc_scores),1)}%) scored 0 on location — likely missing or unrecognised location text.")
    add("  - Fix: ensure Apify actors populate `location` field; consider expanding `region_for_text` keyword map in `locations.py`.")
    add("")

add("### Tuning recommendations")
add("")
add("1. **Review downgrades list (§2a):** If legitimate jobs appear, the experience or location weight may be too punishing. Consider softening the experience hard-gate from `profile+2y` to `profile+3y`.")
add("2. **Review hard-fail overrides (§3):** Any job where the LLM gave A/S but the engine forces F is worth manual inspection — the LLM sometimes sees context the structured fields miss.")
add("3. **Expand skill aliases (matching.py):** Common tech in B/C/F jobs (§6) that overlaps with profile core skills but under different names → add to `_SKILL_ALIASES`.")
add("4. **Location data quality:** Many jobs arrive with empty `location`. Improve `persistence.detect_job_location()` by scanning more Apify raw fields (`headquarters`, `remote`).")
add("5. **Salary signal:** Currently only nudges ±5 pts; if salary data coverage is low (check §4 signals), verify `salary_yen` is populated in more jobs.")

# ── Write output ──────────────────────────────────────────────────────────
report_path = Path(__file__).parent.parent / "ranking_audit_report.md"
report_text = "\n".join(lines)
report_path.write_text(report_text)
print(f"\nReport written to {report_path}", file=sys.stderr)
print(report_text[:500])  # preview
