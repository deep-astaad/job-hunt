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
    "AI Engineer",
    "API Engineer",
    "Backend Engineer",
    "Cloud Engineer",
    "Data Engineer",
    "DevOps Engineer",
    "Django Engineer",
    "Full Stack Engineer",
    "Go Engineer",
    "Infrastructure Engineer",
    "Machine Learning Engineer",
    "Platform Engineer",
    "Python Engineer",
    "Site Reliability Engineer",
    "Software Engineer",
    "Solutions Architect",
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
    # Japan: bias toward English-speaking roles (most JP listings need Japanese).
    append_english = loc_cfg.get("region") == "japan"
    urls = [_linkedin_url(r, loc_cfg, append_english) for r in ROLES]
    return {
        "actor_id": "curious_coder/linkedin-jobs-scraper",
        "source": "linkedin",
        "location": loc_cfg["id"],
        "schedule_frequency": loc_cfg.get("schedule_frequency", "daily"),
        "input": {
            "count": 100,
            "scrapeCompany": False,
            "splitByLocation": False,
            "splitCountry": loc_cfg.get("country", "") or "JP",
            "urls": urls,
            "saveOnlyUniqueItems": True,
        },
        # Cross-source redundancy: if LinkedIn fails, pull the same location via Indeed.
        "fallback_actors": [
            {
                "actor_id": "bebity/linkedin-jobs-scraper",
                "input": {"urls": urls, "count": 100, "scrapeCompany": False},
            }
        ],
    }


def _indeed_config(loc_cfg):
    english_clause = ' AND ("English")' if loc_cfg.get("region") == "japan" else ""
    position = (
        '("Software Engineer" OR "Software Developer" OR "Backend Engineer" OR '
        '"Cloud Engineer" OR "DevOps" OR "Python" OR "Platform Engineer")'
        + english_clause
    )
    inp = {
        "followApplyRedirects": False,
        "maxItemsPerSearch": 150,
        "parseCompanyDetails": False,
        "position": position,
        "saveOnlyUniqueItems": True,
    }
    country = loc_cfg.get("indeed_country", "")
    if country:
        inp["country"] = country
    location = loc_cfg.get("indeed_location", "")
    if location:
        inp["location"] = location
    return {
        "actor_id": "misceres/indeed-scraper",
        "source": "indeed",
        "location": loc_cfg["id"],
        "schedule_frequency": loc_cfg.get("schedule_frequency", "daily"),
        "input": inp,
    }


def _japan_niche_configs(loc_cfg):
    """Japan-specific English-friendly boards (japan-dev, tokyo-dev, daijob)."""
    freq = loc_cfg.get("schedule_frequency", "daily")
    return [
        {
            "actor_id": "jungle_synthesizer/japan-dev-scraper",
            "source": "japan_dev", "location": loc_cfg["id"], "schedule_frequency": freq,
            "input": {"maxItems": 150, "searchQuery": "Python"},
        },
        {
            "actor_id": "jungle_synthesizer/tokyo-dev-scraper",
            "source": "tokyo_dev", "location": loc_cfg["id"], "schedule_frequency": freq,
            "input": {
                "japaneseRequired": "no-japanese-required", "maxItems": 150,
                "proxyConfiguration": {"useApifyProxy": False}, "scrapeMode": "jobs",
            },
        },
    ]


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
        # configs.append(_indeed_config(cfg))
        # if cfg.get("region") == "japan":
        #     configs.extend(_japan_niche_configs(cfg))
    return configs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="print to stdout instead of writing actor-config.json")
    args = parser.parse_args()

    configs = build()
    text = json.dumps(configs, indent=2)
    if args.print_only:
        print(text)
        return
    out_path = os.path.join(BASE_DIR, "actor-config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"Wrote {len(configs)} actor configs across "
          f"{len(set(c['location'] for c in configs))} locations -> {out_path}")


if __name__ == "__main__":
    main()
