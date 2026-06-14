# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

An asynchronous pipeline that scrapes job listings (via Apify actors), formats and ranks them against user resume profiles (via OpenAI), persists everything in MySQL through a Django REST API, and notifies the user on Discord. Celery + Redis drive the async work. Aimed at Tokyo/Japan tech roles.

## Architecture

The repo is **two independent codebases**:

- **Root** — the pipeline. Python at repo root (`tasks/`, `config.py`, `persistence.py`, `ranker.py`, `matching.py`, `locations.py`, `llm.py`, `outputs.py`, `build_actor_configs.py`, `celery_app.py`) plus the Django app under `backend/`. All these run from the same Docker image, switched by `APP_MODE`.
- **`japan-tech-scraper/`** — a standalone Apify actor (its own Docker image, deployed to Apify). It has its own `AGENTS.md`/`CLAUDE.md`; treat it as a separate project.

### One image, five roles (`entrypoint.sh` + `APP_MODE`)

`docker-compose.yml` builds one image and runs it in several modes via the `APP_MODE` env var: `web` (Django `runserver`, runs migrations first), `celery-worker`, `celery-beat` (uses `django_celery_beat` DatabaseScheduler), `celery-flower` (monitoring on :5555→host :5556), and `job-finder` (one-off `python main.py`). The Django web container maps host **8080 → 8000**.

### Process boundary: Celery tasks talk to Django over HTTP, not the ORM

The Celery side (`tasks/`, `persistence.py`) is **not** a Django app. It persists by calling the Django REST API over HTTP (`DjangoPersistence` in `persistence.py`, hitting `/api/jobs/bulk_create/`, `/api/rankings/bulk_create/`, etc.). The exception is a few tasks in `tasks/pipeline.py` (e.g. `process_unprocessed_jobs_task`) that import Django models directly — this works only because `celery_app.py` calls `django.setup()` and puts both repo root and `backend/` on `sys.path`. When adding pipeline logic, prefer the HTTP API; reach for the ORM only when already inside a task that uses it.

### The async pipeline (`tasks/pipeline.py`)

Nothing blocks waiting on a scraper. Flow:

1. **`schedule_daily_scrapers`** (Celery Beat entry point) reads `actor-config.json`, filters actors by `schedule_frequency` (`daily` / `every_2_days` / `weekly`), and calls `run_pipeline`.
2. **`run_pipeline`** mints a `pipeline_run_id` (uuid), seeds Redis counters, schedules the reconciler, and spawns one **`start_actor`** per config.
3. **`start_actor`** launches the Apify actor and dispatches **`poll_actor_dataset`**.
4. **`poll_actor_dataset`** is a self-retrying task that pages through the actor's dataset (`offset` carried in retry kwargs). For each new job it saves a stub, skips if `is_formatted` is already true, takes a Redis lock, and dispatches a `chain(format_and_persist_job → rank_job_multi_profile)`. It retries until the actor reaches a terminal status AND no new items remain.

Routing: `format_and_persist_job` → `formatting` queue, `rank_job_multi_profile` → `ranking` queue (see `celery_app.py` `task_routes`). The worker pool is `--pool=threads` (OpenAI calls are IO-bound).

### Completion tracking is Redis-based and must stay idempotent

This is the subtle part. Per-run Redis keys: `pipeline:{id}:active_actors`, `:in_flight` (a SET of job ids), `:dispatched_at` (hash), `:total_jobs`, `:summary_sent`. A job is removed from `in_flight` via atomic `SREM` exactly when its ranking finishes (`_check_and_trigger_discord` in `tasks/ranking.py`). When `active_actors <= 0` and `in_flight` is empty, the summary fires **once**, guarded by `SET :summary_sent nx ex=86400`.

Because Celery retries and re-deliveries can double-fire, every decrement/removal is designed to be idempotent — preserve that when editing. **`check_pipeline_completion`** is a watchdog reconciler that sweeps `in_flight` jobs stuck > 300s (worker crashes, lost tasks) so the summary can't hang forever. `job_processing_lock:{job_id}` (NX, 1h TTL) prevents concurrent duplicate processing of the same job.

### Two distinct Discord notifications

- **Immediate**: in `rank_job_multi_profile`, any S/A-tier result posts right away via `outputs.ExportHandler.post_single_job_to_discord`.
- **Summary**: `send_discord_summary` fires once at full pipeline completion.

### Ranking: deterministic engine + LLM blend (`matching.py`)

Ranking is **not** LLM-only. `tasks/ranking.py` sends the LLM the **full** job
description + tech stack + location (previously it truncated to 200 chars), then
fuses that with a deterministic, explainable engine:

- **`matching.compute_match(profile, job, location_cfgs)`** scores a job/profile pair
  0–100 across weighted signals — skill overlap (canonicalized via an alias map +
  description vocab scan), title/role-family affinity, experience fit, language fit,
  location fit, salary — and applies the **hard gates** (required non-English
  language the candidate lacks, internships, experience > profile+2y, senior/lead
  titles, out-of-target location). It returns `tier`, numeric `score`, `hard_fail`,
  and a `signals` diagnostics dict.
- **`matching.blend_with_llm(deterministic, llm_tier)`** fuses the two: a
  deterministic hard-fail always wins (→F); otherwise blends 60% deterministic /
  40% LLM into a final tier + score. This keeps ranking robust even when the LLM is
  mocked, rate-limited, or a small local model.

`_apply_matching_engine` in `tasks/ranking.py` runs this per profile and persists
`match_tier`, `llm_tier` (raw), `deterministic_tier`, `match_score` (0–100, drives
intra-tier `rank = 100 - score`), and `signals`. The old `_apply_hard_rules_multi`
regex is gone; gates now live in `matching.py` and are **location-aware**.
`detect_job_language`/`detect_job_location` in `persistence.py` infer language (JP
from CJK/keywords) and a free-text location from raw scraper fields + text.

### Target locations (`locations.json` + `locations.py`)

`locations.json` defines selectable target regions (Japan/Tokyo, Remote, India,
Europe, US, …) with aliases, LinkedIn geoIds, and Indeed country/location used for
scraping. `active` lists live locations; each profile in `user-profiles.json` may
narrow via `target_locations` (ids or `"all"`) and declares `languages`,
`experience_years`, `min_salary_yen`. `Job` now stores `location`/`region`/
`country`/`is_remote` (derived in `models.save()` via `parsers.parse_location_region`).
The dashboard has a Location filter; the API `JobFilter` exposes `region`/`country`/
`is_remote`. **`build_actor_configs.py`** generates `actor-config.json` from
`locations.json` + a curated role list — re-run it after editing either.

### Apify fallbacks & LLM fallback

- Actor configs may carry `fallback_actors`; `tasks/pipeline.start_actor` tries the
  primary then each fallback before counting an actor as lost (survives quota/outage).
- `llm.chat_completion()` wraps the OpenAI call with an optional **fallback provider**
  (e.g. local Ollama). Configure `OPENAI_FALLBACK_BASE_URL` / `_MODEL` / `_API_KEY`
  via the settings modal or env; empty base URL = disabled (default), so existing
  deployments are unchanged. Recommended local model for 6GB VRAM: `qwen3.5:4b`.
  Note: wiring Ollama requires the worker to reach it on the network (it's on a
  separate Docker network by default).

### Data model (`backend/jobs/models.py`)

`Job` is deduplicated by `url_hash` (SHA-256 of url, unique) — bulk_create does `update_or_create` on it. Job lifecycle flags: `is_formatted` → `is_ranked` → `alert_sent`. Two invariants live in `save()`: a `Job` with `is_formatted=False` always resets `is_ranked=False`; saving a `JobRanking` flips its job's `is_ranked=True`. `Job` also carries `location`/`region`/`country`/`is_remote` (region/country/remote derived in `save()`). `JobRanking` is unique per `(job, profile_id)` with tiers S/A/B/C/F, plus `llm_tier`, `deterministic_tier`, `match_score` (0–100), and `signals` (JSON diagnostics). Migrations follow an **idempotent MySQL DDL** pattern (see 0007/0008) so a half-applied migration self-heals.

### Dynamic config (`config.py`)

Secrets (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `APIFY_API_TOKEN`) resolve from a Redis hash `app_settings` first, falling back to env vars. They're editable at runtime via the admin-only `/api/settings/` endpoint and the dashboard settings modal — so changing keys does **not** require a redeploy. The OpenAI-compatible client means any base URL works (DeepSeek, local vLLM, etc.); `test_llm.py` verifies a given endpoint/model.

### Config files (repo root)

- `actor-config.json` — which Apify actors to run, their input payloads, and `schedule_frequency`. (`example.actor-config.json` is the template.)
- `user-profiles.json` — the resume profiles jobs are ranked against; each has an `id` used as `profile_id` throughout. `main.py` and the pipeline filter by these ids.
- `prompts/` — LLM system prompts: `formatter.txt`, `ranker.txt`, `batch_ranker.txt`.

## Commands

All app commands run inside containers. Django lives in `backend/`, so `manage.py` calls need `-w /app/backend`.

```bash
# Full stack (mysql, redis, django, celery worker/beat/flower)
docker compose up -d --build

# Migrations & superuser (Django runs from /app/backend)
docker compose exec -w /app/backend django python manage.py migrate
docker compose exec -w /app/backend django python manage.py createsuperuser
docker compose exec -w /app/backend django python manage.py makemigrations

# Django tests (run from backend/)
docker compose exec -w /app/backend django python manage.py test
docker compose exec -w /app/backend django python manage.py test jobs.tests.JobModelTests
docker compose exec -w /app/backend django python manage.py test jobs.tests.JobModelTests.test_save_resets_is_ranked_when_unformatted

# Pipeline / Redis-logic tests (run from /app in the worker; need a live Redis)
docker compose exec celery-worker python -m unittest scratch.test_pipeline

# Matching engine + ranking-integration unit tests (pure Python, no DB/Redis/network)
docker compose exec celery-worker python -m unittest scratch.test_matching
docker compose exec celery-worker python -m unittest scratch.test_ranking_integration

# Run anything WITHOUT the stack / without touching MySQL (host, uv):
#   DJANGO_TEST_SQLITE=1 uses a throwaway sqlite DB. APP_MODE=celery-worker +
#   dummy APIFY/OPENAI keys let config.py import. Used to test this branch in
#   isolation from the live deployment (which mounts this repo via docker-compose).
DJANGO_TEST_SQLITE=1 APP_MODE=celery-worker APIFY_API_TOKEN=x OPENAI_API_KEY=x \
  uv run --project . python backend/manage.py test jobs   # (cd backend first)
uv run python -m unittest scratch.test_matching

# Regenerate actor-config.json from locations.json + role list
python build_actor_configs.py            # --print to preview

# Trigger the pipeline manually (instead of waiting for Beat)
docker compose exec celery-worker python main.py

# Re-process all unformatted/unranked jobs in the DB
docker compose exec celery-worker python backfill.py

# Inspect Celery
docker compose exec celery-worker celery -A celery_app inspect active
# Flower UI: http://localhost:5556

# Dependencies are managed with uv (Python 3.13)
uv sync
```

Mock the LLM (no API calls, simulated latency/fallbacks) by setting `MOCK_LLM=1` — used in `format_and_persist_job` and `rank_job_multi_profile`.

### Scheduling

Schedules are **not** in code. `schedule_daily_scrapers` is registered as a periodic task through the Django admin (`/admin/` → django-celery-beat Crontabs + Periodic Tasks); `actor-config.json` only decides which actors run on a given day.

## Endpoints

- Frontend dashboard: `/` (Django-rendered, `jobs/web_views.py`, `jobs/web_urls.py`) — server-side, infinite-scroll via `?ajax=1`.
- Django admin: `/admin/`
- REST API: `/api/jobs/`, `/api/rankings/`, `/api/settings/`. Key custom actions: `jobs/bulk_create/`, `jobs/stats/`, `jobs/today-ranked/`, `jobs/mark_alerts_sent/`, `rankings/bulk_create/`, `rankings/update_ranks/`.
</content>
