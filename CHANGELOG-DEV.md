# Developer Changelog

Technical notes for contributors. User-facing summary: [CHANGELOG.md](CHANGELOG.md).

## v1.0.1 — 2026-06-20 — Critical pipeline persistence hotfix (PR #39)

Follow-up remediation after the production validation pass for issues #34-#38.

### Source validation / local scrapers
- `Job.SOURCE_CHOICES` now includes every live scraper source slug:
  `gaijinpot`, `careercross`, `green`, `wantedly`, plus legacy
  `japan-dev` / `tokyodev` so existing rows remain patchable before cleanup.
- Migration `0010_update_source_choices` updates the model choices.
- `local_scrapers.py` now emits canonical `japan_dev` and `tokyo_dev` slugs.

### Formatter/ranker persistence semantics
- `tasks.formatting.format_and_persist_job` now raises/retries persistence
  failures instead of returning falsey data into the ranking chain.
- Permanent formatter HTTP failures release pipeline/processing state before
  re-raising; transient request failures retry with exponential backoff.
- Required text fields from the formatter (`title`, `company`, `url`, `source`)
  are backfilled from the original scraped job when the LLM returns blank values.
- `tasks.ranking._persist_rankings` now calls `raise_for_status()` and propagates
  failures; ranker retry/fatal paths clear `job_processing_lock:{job_id}`.
- Pipeline dispatch now passes `pipeline_run_id` through formatter payloads so
  completion tracking can reconcile failed jobs.

### Batch ingestion recovery
- New `tasks.pipeline._save_jobs_with_fallback` keeps the fast bulk save path but
  retries missing URLs individually when the bulk request fails or returns an
  incomplete `{normalized_url: {id, is_formatted}}` map.
- This covers the production failure mode where Django committed rows but the
  worker lost the response map and skipped dispatch, leaving fresh jobs
  unformatted.

### API ordering / data repair
- `JobViewSet` list queries now default to `order_by("-scraped_at", "-id")`.
- `best_tier` ordering has the same deterministic tie-breakers.
- Production active data was repaired outside the migration:
  - active URL/hash mismatches: 0 after cleanup
  - active duplicate normalized URL groups: 0 after cleanup
  - missing active profile rankings: 0 after rerank
  - formatted-but-unranked active jobs: 0 after rerank

### Tests
- Added `SourceChoicesTests`, `FormattingTaskPersistenceTests`,
  `RankingTaskPersistenceTests`, and `PipelineBatchPersistenceTests`.
- Run:
  `python3 -m py_compile backend/jobs/models.py backend/jobs/views.py tasks/formatting.py tasks/ranking.py tasks/pipeline.py local_scrapers.py`
- Run:
  `MOCK_LLM=1 DJANGO_TEST_SQLITE=1 APP_MODE=celery-worker APIFY_API_TOKEN=x OPENAI_API_KEY=x uv run --project . python backend/manage.py test jobs`

## v1.0.0 — 2026-06-20 — Audit-hardening batch (PRs #20–#32)

Thirteen audit findings from `PIPELINE_AUDIT.md`, each reviewed (freelancer +
second pass) and merged. Grouped by area below; PR numbers in parentheses.

### Ranking / matching engine
- **(#30) `matching.title_affinity`** — bare `Software Engineer`/`Software Developer`
  removed from the `backend`/`fullstack` role families; a new `_GENERIC_ROLE_KWS`
  fallback returns `0.6` (was implicitly `1.0`). Specific/contextual titles still
  score `1.0`.
- **(#21) Thread-safety** — stopped mutating the shared, cached profile dicts in
  `tasks/ranking.py` (worker pool is `--pool=threads`). `experience_years` is read
  as the float already in `user-profiles.json`; the integer-truncating
  `JobRankerAI._parse_experience_years` is out of the live/backfill path.
- **(#24) Dead code** — removed legacy `_parse_ranking_table` / `_apply_hard_rules`
  / `_parse_experience_years` and related markdown-table parsers that contradicted
  the deterministic engine.
- **(#32) Robustness nits** — `_load_profiles_for_ranking` cache check uses
  `hasattr(..., "cache")` (empty cache no longer forces re-reads); `rankings = []`
  initialised before the try so the return path never relies on `locals()`.

### Persistence / dedup
- **(#31) `normalize_url`** — per-domain identity-param allowlist
  (`_DOMAIN_ID_PARAMS`: Indeed `jk`, Taleo `job`, Jobvite `j`, SuccessFactors
  `jobId`, Workable `jid`, SmartRecruiters `job`). Exact host/subdomain match
  (`host == domain or host.endswith("." + domain)`) — no more substring matches
  like `notindeed.com`. **Both copies kept byte-identical** (`persistence.py` and
  `backend/jobs/parsers.py`); a parity test asserts this. **Migration `0009`**
  recomputes `url_hash` for existing rows on the new ATS domains (collision-safe,
  no-op when none exist) so the normalization change can't fork dedup keys.
- **(#29) `detect_job_language`** — delegates to
  `matching.detect_required_language` and is gated on the `is_hard` flag: `JP`
  only when Japanese is a hard requirement, `non-english` only for hard non-English,
  else `EN`. Label now means "required working language".
- **(#22) Batch stub save** — `bulk_create` returns a `{normalized_url: {id,
  is_formatted}}` map; the poller dispatches from that map instead of an N+1
  GET-per-item. Dedup invariants preserved (skip already-formatted, lock before
  dispatch, `in_flight`/`dispatched_at`/`total_jobs` before the chain, duplicate
  URLs collapse via `stub_by_url`).

### Pipeline / cost control
- **(#20) Pre-screen guaranteed-F** — `matching.prescreen_hard_fail` runs the hard
  gates on raw scraper data before any LLM call; `_persist_prescreen_f` is now
  **atomic**: POST F rankings → `raise_for_status` → flip `is_formatted`+`is_ranked`
  in one patch. On rankings-POST failure it returns `False` (flags untouched) so
  the caller falls back to the normal format+rank chain — no formatted-but-unranked
  orphans.
- **(#23) Formatter JSON mode** — `JobFormatter.format_job` passes
  `response_format={"type":"json_object"}` and drops the markdown-fence stripping,
  matching the ranker path.

### Notifications
- **(#25) Discord** — `post_single_job_to_discord` calls `raise_for_status()`
  before `mark_alerts_sent`, so 429/4xx/5xx no longer falsely mark a job alerted;
  the summary batch path (`_send_batches` + regional sends) does the same and skips
  the bulk `mark_alerts_sent` on failure. `send_discord_summary` is wired to
  `ExportHandler.post_tiered_jobs_from_api` (was a no-op).

### Scraper configuration (`build_actor_configs.py` → `actor-config.json`)
- **(#27) Cost cap** — `ROLES` pruned 34 → 16 de-aliased queries; per-search
  `count` 400 → 100 (~88% fewer max items/run).
- **(#28) Indeed** — re-enabled as a second source per active location
  (`maxItemsPerSearch=150`); Japan niche actors stay disabled (local scrapers
  cover them).
- **(#26/#27) `append_english`** — restored the English-keyword bias for Japan
  LinkedIn searches. `actor-config.json` is generated — re-run
  `uv run python build_actor_configs.py` after editing the generator or
  `locations.json`.

### Tests & migrations
- New: `NormalizeUrlTests` (parity across both normalizers + substring guard),
  `PrescreenPersistTests` (partial-failure & success paths),
  `DiscordAlertMarkingTests` (failed-post must not mark sent), plus matching-engine
  cases for the title-affinity discount and the optional-JP → EN label.
- Migration `0009_recompute_ats_url_hash`.
- Run: `uv run python -m unittest scratch.test_matching scratch.test_ranking_integration`
  and `DJANGO_TEST_SQLITE=1 APP_MODE=celery-worker APIFY_API_TOKEN=x OPENAI_API_KEY=x
  MOCK_LLM=1 uv run --project . python backend/manage.py test jobs`.

### Notes
- Deploy is image-based (GitHub Actions → ghcr → watchtower); migration `0009`
  runs on the next deploy's `migrate` step. See [HANDOVER.md](HANDOVER.md).
