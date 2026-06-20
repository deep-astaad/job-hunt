# Changelog

User-facing behaviour changes. For internal/technical notes see
[CHANGELOG-DEV.md](CHANGELOG-DEV.md).

## v1.0.1 — 2026-06-20 — Pipeline persistence hotfix

This bugfix release closes the production reliability issues found during the
final post-merge validation pass.

### Scrape → format → rank is safer
- **Real job-board sources are accepted end to end.** GaijinPot, CareerCross,
  Green, Wantedly, and legacy local scraper source names no longer fail
  formatting updates because of rejected source values.
- **Fresh jobs are no longer silently orphaned after a bulk save hiccup.** If the
  backend saves jobs but the worker loses the bulk response, the worker now
  recovers each job id and still dispatches formatting/ranking.
- **Formatter and ranker persistence failures now fail loudly and retry.** A
  temporary API/database problem no longer looks like successful processing.
- **Processing locks are released on fatal failures.** Jobs do not stay stuck in
  Redis after an unrecoverable formatter or ranker error.
- **Blank AI output is patched from the original scraped job.** Required fields
  like company, URL, and source fall back to scraper data when the formatter
  returns blanks.

### Data and API cleanup
- **Production active URL hashes and duplicates were repaired.** Active rows now
  match the current normalizer, duplicate normalized URLs were deactivated, and
  current active jobs have complete profile rankings.
- **Job list pagination is stable.** API list pages now use deterministic
  ordering so repeated pagination does not drift.

_No action required beyond deploying this release._

## v1.0.0 — 2026-06-20 — Ranking accuracy & alert reliability

This release is a quality-and-reliability pass over the scrape → rank → notify
pipeline. What you'll actually notice:

### Ranking is more accurate
- **Generic job titles no longer get a free pass.** A vague "Software Engineer"
  or "Software Developer" title is no longer scored as if it were a specific
  backend/full-stack match — it now has to earn its tier from the skills,
  description, and experience fit. Specific titles (e.g. "Backend Engineer", or
  "Software Engineer (Backend)") are unaffected.
- **Japanese-language tagging is fixed.** Jobs are only labelled **JP** when
  Japanese is genuinely *required*. Postings that merely mention Japanese as a
  nice-to-have, or that just contain a Japanese address, now stay **EN**. The
  dashboard **Language** filter is correspondingly more trustworthy.

### Discord alerts are more reliable
- **Failed alerts are no longer silently lost.** If Discord rejects a post
  (rate-limited, error, etc.), the job is no longer wrongly marked as "alerted",
  so the end-of-run summary still picks it up as a backstop.
- **The end-of-run summary actually posts now.** Pipeline-completion summaries of
  the day's top S/A jobs are sent to Discord (previously this was a no-op).

### Better job coverage & fresher results
- **Indeed is back as a second source** alongside LinkedIn for each active region,
  so you see a wider spread of postings.
- **Japan searches are biased toward English-friendly roles** again.
- **Duplicate listings from applicant-tracking sites are handled correctly.**
  Postings hosted on Taleo, Jobvite, SuccessFactors, Workable, and SmartRecruiters
  are no longer collapsed into one entry — distinct jobs stay distinct, and
  re-scrapes update the existing entry instead of creating duplicates.

### Faster and cheaper behind the scenes
- Jobs that can't possibly match (wrong required language, internships, senior/lead
  roles, out-of-region) are screened out *before* the expensive AI steps. They're
  still recorded as **F-tier** — you just get them sooner and at lower cost.
- The scraping pipeline does less redundant work per run, so results land faster.

_No action required — these take effect automatically on the next deployment._
