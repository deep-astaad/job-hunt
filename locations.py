"""Loader + helpers for locations.json (target locations).

Pure-Python and side-effect free so it can be imported from Celery tasks, Django
views, and unit tests. Falls back gracefully to a single Tokyo default if the
config file is missing, preserving the project's original behaviour.
"""
from __future__ import annotations

import json
import os

_DEFAULT = {
    "active": ["japan_tokyo"],
    "locations": {
        "japan_tokyo": {
            "id": "japan_tokyo", "label": "Tokyo, Japan", "region": "japan",
            "country": "JP", "city": "Tokyo", "remote": False,
            "local_language": "japanese", "local_language_hard_fail": True,
            "aliases": ["tokyo", "japan", "jp"],
            "linkedin_geo_id": "103925994", "linkedin_location": "Tokyo, Japan",
            "indeed_country": "JP", "indeed_location": "Tokyo",
            "linkedin_scrape_limit": 500, "indeed_scrape_limit": 1000,
        }
    },
}

_cache = None


def _config_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations.json")


def load_locations(force=False):
    """Return the parsed locations config (cached)."""
    global _cache
    if _cache is not None and not force:
        return _cache
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "locations" not in data:
            raise ValueError("malformed locations.json")
        _cache = data
    except Exception:
        _cache = _DEFAULT
    return _cache


def all_locations():
    return load_locations().get("locations", {})


def active_location_ids():
    cfg = load_locations()
    ids = cfg.get("active") or list(cfg.get("locations", {}).keys())
    return [i for i in ids if i in cfg.get("locations", {})]


def get_location(loc_id):
    return all_locations().get(loc_id)


def location_cfgs_for_profile(profile):
    """Resolve the list of location config dicts a profile targets.

    Profile may set `target_locations` to a list of ids or the string "all".
    Unknown / unset -> the globally active locations.
    """
    locs = all_locations()
    targets = profile.get("target_locations") if profile else None

    if targets in (None, "", "all", ["all"]):
        ids = active_location_ids()
    elif isinstance(targets, str):
        ids = [targets]
    elif isinstance(targets, list):
        ids = targets
    else:
        ids = active_location_ids()

    cfgs = [locs[i] for i in ids if i in locs]
    return cfgs or [locs[i] for i in active_location_ids() if i in locs]


def region_for_text(text):
    """Best-effort (region, country, city) from a free-text location string.

    Returns (region, country, city) where any element may be "" if unknown.
    """
    if not text:
        return "", "", ""
    import re
    blob = str(text).lower()
    for cfg in all_locations().values():
        # "remote" is a work arrangement, not a place; detect_remote() handles it.
        # Prefer a concrete region so "remote, team in Bangalore" classifies as india.
        if cfg.get("remote"):
            continue
        for alias in cfg.get("aliases", []) + [cfg.get("city", ""), cfg.get("country", "")]:
            alias = str(alias or "").strip().lower()
            if alias:
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, blob):
                    return cfg.get("region", ""), cfg.get("country", ""), cfg.get("city", "")
    return "", "", ""
