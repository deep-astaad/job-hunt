"""Offline ranking-quality analyzer.

Runs the CURRENT matching engine against the exported 13k-job DB snapshot and
surfaces likely false positives / false negatives / wrong ranks for inspection.

We have no human-labelled ground truth, so "false positive/negative" is inferred
from objective heuristics about what these specific profiles want (junior/mid,
English-OK, Tokyo or remote, backend/devops/fullstack) plus disagreement between
the deterministic engine and the LLM tier stored in the DB.

Usage:
    uv run python -m scratch.analyze_ranking            # full report
    uv run python -m scratch.analyze_ranking <profile>  # one profile
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

import matching
from locations import location_cfgs_for_profile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPORT = os.path.join(HERE, "data", "jobs_export.json")
OUT_DIR = os.path.join(HERE, "data")

TIER_RANK = {t: i for i, t in enumerate(matching.TIER_ORDER)}  # S=0 .. F=4


def load():
    profiles = json.load(open(os.path.join(ROOT, "user-profiles.json")))
    data = json.load(open(EXPORT))
    return profiles, data["jobs"], data["rankings"]


def stored_rankings_index(rankings):
    """(job_id, profile_id) -> stored ranking dict."""
    idx = {}
    for r in rankings:
        idx[(r["job_id"], r["profile_id"])] = r
    return idx


# --- heuristic red/green flags used to *infer* FP/FN without ground truth ---
_JP_REQ = re.compile(r"(日本語|jlpt|n1|n2|nihongo|japanese.{0,30}(require|mandatory|fluent|native|business))", re.I)
_SENIOR = matching._SENIOR_TITLE_RE
_JUNIOR = matching._JUNIOR_TITLE_RE
_INTERN = matching._INTERN_RE
_TECH_TITLE = re.compile(
    r"(engineer|developer|programmer|sre|devops|architect|data scien|software|backend|"
    r"front[- ]?end|full[- ]?stack|platform|infrastructure|cloud|machine learning|ml |ai )",
    re.I,
)


def job_text(j):
    return " ".join(str(j.get(k) or "") for k in ("title", "description", "full_description")).lower()


def looks_tech(j):
    return bool(_TECH_TITLE.search(str(j.get("title") or "")))


def analyze(profiles, jobs, rankings, only_profile=None):
    stored = stored_rankings_index(rankings)
    report = {}

    for p in profiles:
        pid = p["id"]
        if only_profile and pid != only_profile:
            continue
        loc_cfgs = location_cfgs_for_profile(p)

        tier_dist = Counter()
        hardfail_reasons = Counter()
        det_vs_llm = Counter()           # (det_tier, llm_tier)
        big_disagree = []                # |det - llm| >= 2 tiers
        susp_fp = []                     # high tier but red flags
        susp_fn = []                     # F/C but looks like a great fit
        signal_zero = Counter()          # how often each signal is ~0
        results = []

        for j in jobs:
            res = matching.compute_match(p, j, loc_cfgs)
            tier = res["tier"]
            tier_dist[tier] += 1
            sig = res["signals"]
            if res["hard_fail"]:
                hardfail_reasons[res["hard_fail_reason"]] += 1
            for k in ("skill", "title", "experience", "language", "location"):
                if sig.get(k, 1) <= 0.05:
                    signal_zero[k] += 1

            st = stored.get((j["id"], pid))
            llm_tier = (st or {}).get("llm_tier")
            results.append((j, res, st))

            if llm_tier in TIER_RANK:
                det_vs_llm[(tier, llm_tier)] += 1
                gap = TIER_RANK[tier] - TIER_RANK[llm_tier]
                if abs(gap) >= 2:
                    big_disagree.append((j, res, llm_tier, gap))

            txt = job_text(j)
            title = str(j.get("title") or "")
            # ---- inferred FALSE POSITIVE: engine says S/A but objective red flag
            if tier in ("S", "A"):
                flags = []
                if _SENIOR.search(title) and not _JUNIOR.search(title):
                    flags.append("senior-title")
                if _INTERN.search(title):
                    flags.append("intern-title")
                if _JP_REQ.search(txt):
                    flags.append("jp-required-text")
                if not looks_tech(j):
                    flags.append("non-tech-title")
                if sig.get("skill", 1) <= 0.1:
                    flags.append("near-zero-skill")
                if flags:
                    susp_fp.append((j, res, flags))

            # ---- inferred FALSE NEGATIVE: engine says F/C but looks like strong fit
            if tier in ("F", "C"):
                green = []
                if sig.get("skill", 0) >= 0.5:
                    green.append("high-skill")
                if sig.get("title", 0) >= 0.9:
                    green.append("title-match")
                if sig.get("experience", 0) >= 0.8 and not res["hard_fail"]:
                    green.append("exp-ok")
                # strong fit but only knocked down by location/language fuzziness
                strong = sig.get("skill", 0) >= 0.5 and sig.get("title", 0) >= 0.9
                if strong:
                    susp_fn.append((j, res, res.get("hard_fail_reason"), green))

        report[pid] = {
            "tier_dist": tier_dist,
            "hardfail_reasons": hardfail_reasons,
            "det_vs_llm": det_vs_llm,
            "big_disagree": big_disagree,
            "susp_fp": susp_fp,
            "susp_fn": susp_fn,
            "signal_zero": signal_zero,
            "n": len(jobs),
        }
    return report


def pct(n, d):
    return f"{100*n/d:5.1f}%" if d else "  n/a"


def print_report(report):
    for pid, r in report.items():
        n = r["n"]
        print("\n" + "=" * 78)
        print(f"PROFILE: {pid}   (n={n} jobs)")
        print("=" * 78)
        print("Tier distribution (current engine):")
        for t in matching.TIER_ORDER:
            c = r["tier_dist"].get(t, 0)
            print(f"   {t}: {c:6d}  {pct(c,n)}")
        print("\nHard-fail reasons:")
        for reason, c in r["hardfail_reasons"].most_common():
            print(f"   {c:6d}  {reason}")
        tot_hf = sum(r["hardfail_reasons"].values())
        print(f"   TOTAL hard-fail: {tot_hf}  {pct(tot_hf,n)}")
        print("\nSignals near-zero (<=0.05) counts:")
        for k, c in r["signal_zero"].most_common():
            print(f"   {k:12s} {c:6d}  {pct(c,n)}")

        print(f"\nInferred FALSE POSITIVES (S/A with red flags): {len(r['susp_fp'])}")
        fp_flag = Counter()
        for _, _, flags in r["susp_fp"]:
            for f in flags:
                fp_flag[f] += 1
        for f, c in fp_flag.most_common():
            print(f"   {c:6d}  {f}")

        print(f"\nInferred FALSE NEGATIVES (F/C but skill>=.5 & title>=.9): {len(r['susp_fn'])}")
        fn_reason = Counter((reason or "no-hard-fail") for _, _, reason, _ in r["susp_fn"])
        for reason, c in fn_reason.most_common():
            print(f"   {c:6d}  knocked-down-by: {reason}")

        print(f"\nBig det<->LLM disagreements (>=2 tiers): {len(r['big_disagree'])}")
        worse = sum(1 for *_, g in r["big_disagree"] if g > 0)  # det harsher than llm
        better = sum(1 for *_, g in r["big_disagree"] if g < 0)
        print(f"   det HARSHER than llm: {worse}    det MORE generous: {better}")


def dump_samples(report, k=25):
    """Write inspectable JSONL samples for each suspicious bucket."""
    for pid, r in report.items():
        for bucket in ("susp_fp", "susp_fn", "big_disagree"):
            rows = r[bucket]
            path = os.path.join(OUT_DIR, f"{pid}__{bucket}.jsonl")
            with open(path, "w") as f:
                for item in rows[:k]:
                    j, res = item[0], item[1]
                    rec = {
                        "id": j["id"],
                        "title": j.get("title"),
                        "company": j.get("company"),
                        "location": j.get("location"),
                        "region": j.get("region"),
                        "country": j.get("country"),
                        "is_remote": j.get("is_remote"),
                        "language": j.get("language"),
                        "experience_required": j.get("experience_required"),
                        "salary_yen": j.get("salary_yen"),
                        "tech_stack": j.get("tech_stack"),
                        "tier": res["tier"],
                        "score": res["score"],
                        "hard_fail_reason": res["hard_fail_reason"],
                        "signals": {kk: vv for kk, vv in res["signals"].items()
                                    if kk not in ("matched_skills", "missing_skills")},
                        "matched_skills": res["signals"].get("matched_skills"),
                        "desc_head": (j.get("full_description") or j.get("description") or "")[:600],
                    }
                    if bucket == "big_disagree":
                        rec["llm_tier"] = item[2]
                        rec["gap"] = item[3]
                    if bucket == "susp_fp":
                        rec["flags"] = item[2]
                    f.write(json.dumps(rec, default=str) + "\n")
            print(f"wrote {path} ({len(rows[:k])} of {len(rows)})")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    profiles, jobs, rankings = load()
    report = analyze(profiles, jobs, rankings, only_profile=only)
    print_report(report)
    dump_samples(report)
