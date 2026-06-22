#!/usr/bin/env python3
"""Generate actor-config.json from locations.json + a curated role list.

Why: the old actor-config.json hard-coded ~34 Tokyo-only LinkedIn URLs. To
support "target locations" (Japan / Europe / India / remote / ...) the scraper
inputs must be generated per active location instead. This script is the single
source of truth — edit ROLES / locations.json and re-run:

    python build_actor_configs.py            # writes actor-config.json
    python build_actor_configs.py --print     # preview only

Each generated entry carries a `location` id (matching locations.json) and an
optional `fallback_actors` list. tasks/pipeline.start_actor tries the primary
actor first and falls back through that list if it errors (quota/outage), so a
single dead actor no longer silently drops a whole source.

NOTE: fallback actor IDs are best-effort public alternatives; verify they exist
in your Apify account and adjust as needed.
"""

from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Curated roles for the candidate profiles: de-aliased (no Developer/Engineer
# pairs), senior/non-target roles removed, JP-context noise dropped.
# 34 → 16 unique queries; paired with count=100 this cuts Apify volume ~88%.
ROLES = [
    "API Developer",
    "API Engineer",
    "AI Engineer",
    "Application Engineer",
    "Automation Engineer",
    "AWS Engineer",
    "Backend Developer",
    "Backend Engineer",
    "Cloud Engineer",
    "Cloud Solutions Architect",
    "Data Engineer",
    "DevOps Engineer",
    "Django Developer",
    "Django Engineer",
    "Engineering Lead",
    "English Speaking Software Engineer",
    "Full Stack Developer",
    "Full Stack Engineer",
    "Go Engineer",
    "Golang Engineer",
    "Infrastructure Engineer",
    "Machine Learning Engineer",
    "Platform Engineer",
    "Python Developer",
    "Python Engineer",
    "Remote Backend Engineer",
    "Server Side Engineer",
    "Site Reliability Engineer",
    "Software Developer",
    "Software Engineer",
    "Solutions Architect",
    "Systems Engineer",
    "Technical Lead",
    "Web Developer",
]

# Recent-postings window (LinkedIn f_TPR): r86400 = last 24h.
_LINKEDIN_TPR = "r3600"


def _linkedin_url(keyword, loc_cfg, append_english):
    kw = keyword + (" English" if append_english else "")

    url = (
        "https://www.linkedin.com/jobs/search?"
        f"keywords={quote(kw)}"
        f"&location={quote(loc_cfg.get('linkedin_location', ''))}"
        f"&geoId={loc_cfg.get('linkedin_geo_id', '')}"
        f"&f_TPR={_LINKEDIN_TPR}"
    )

    # Add experience levels (default: 2=Entry, 4=Mid-Senior for remote, none for others)
    default_f_e = "2%2C4" if loc_cfg.get("remote") else ""
    f_e = loc_cfg.get("linkedin_f_E", default_f_e)
    if f_e:
        url += f"&f_E={f_e}"

    # Add remote filter if location is remote (2=Remote)
    if loc_cfg.get("remote"):
        url += "&f_WT=2"

    url += "&position=1&pageNum=0"
    return url


def _linkedin_config(loc_cfg):
    append_english = False
    #BUG: Reason to avoid is english jobs do not have english keyword so they are not scraped
    # Japan: bias toward English-speaking roles (most JP listings need Japanese).
    # is_japan = loc_cfg.get("region") == "japan"
    # append_english = is_japan
    urls = [_linkedin_url(r, loc_cfg, append_english) for r in ROLES]
    count = loc_cfg.get("linkedin_scrape_limit", 100)
    return {
        "actor_id": "curious_coder/linkedin-jobs-scraper",
        "source": "linkedin",
        "location": loc_cfg["id"],
        "input": {
            "count": count,
            "scrapeCompany": False,
            "splitByLocation": False,
            "splitCountry": loc_cfg.get("country", "") or "JP",
            "urls": urls,
            "saveOnlyUniqueItems": True,
        },
    }


def _indeed_config(loc_cfg):
    is_japan = loc_cfg.get("region") == "japan"
    if is_japan:
        title = '(Backend OR Python OR Django OR AWS OR DevOps OR "Solutions Architect") ("No Japanese" OR English)'
    else:
        title = '(Backend OR Python OR Django OR AWS OR DevOps OR "Solutions Architect")'
        
    limit = loc_cfg.get("indeed_scrape_limit", 100)
    inp = {
        "country": (loc_cfg.get("indeed_country") or "JP").lower(),
        "datePosted": "1",
        "limit": limit,
        "location": loc_cfg.get("indeed_location", ""),
        "title": title,
    }
    return {
        "actor_id": "valig/indeed-jobs-scraper",
        "source": "indeed",
        "location": loc_cfg["id"],
        "input": inp,
    }

def build():
    with open(os.path.join(BASE_DIR, "locations.json"), "r", encoding="utf-8") as f:
        loc_data = json.load(f)
    locations = loc_data.get("locations", {})
    active = loc_data.get("active") or list(locations.keys())

    configs = []
    for loc_id in active:
        cfg = locations.get(loc_id)
        if not cfg:
            continue
        configs.append(_linkedin_config(cfg))
        configs.append(_indeed_config(cfg))
        # Japan-niche Apify actors (japan-dev, tokyo-dev) are intentionally
        # kept disabled here: run_local_scrapers already scrapes those boards
        # via HTTP with no Apify cost. Re-enabling would double-fetch the same
        # listings (dedup prevents double-processing, but wastes quota).
        # if cfg.get("region") == "japan":
        #     configs.extend(_japan_niche_configs(cfg))
    return configs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="print to stdout instead of writing actor-config.json",
    )
    args = parser.parse_args()

    configs = build()
    text = json.dumps(configs, indent=2)
    if args.print_only:
        print(text)
        return
    out_path = os.path.join(BASE_DIR, "actor-config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(
        f"Wrote {len(configs)} actor configs across "
        f"{len(set(c['location'] for c in configs))} locations -> {out_path}"
    )


if __name__ == "__main__":
    main()
