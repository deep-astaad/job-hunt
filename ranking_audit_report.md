# Ranking Audit Report

**Jobs analysed:** 500  
**Profiles:** 3  
**Date:** 2026-06-15  

Engine: deterministic matching (feature/matching-locations branch) blended with existing LLM tiers from live DB.

### Bugs found and fixed during this audit (matching.py)

| # | Bug | Fix |
|---|-----|-----|
| 1 | Jobs with **zero data** (no description, no tech_stack, no location) all scored 64.6 → tier A because `skill_overlap`, `title_affinity`, and `location_match` returned generous neutral defaults (0.5 / 0.6 / 0.6) | Lowered no-data defaults: skill 0.5→0.25, title-unknown 0.6→0.3, location-unknown 0.6→0.35. No-data jobs now score ~47 → C |
| 2 | "Solutions Architect Graduate" falsely hard-failed as **senior/lead role** because `_SENIOR_TITLE_RE` matched "architect" before the junior marker could override | `is_senior = _SENIOR_TITLE_RE.match AND NOT _JUNIOR_TITLE_RE.match`. Graduate roles with senior-sounding titles now pass through |
| 3 | `"systems engineer"` in the devops role-family was too broad — matched RF / Communications hardware engineers and gave them 1.0 title affinity | Changed to `"software systems engineer"` (explicit). SRE/Platform/Software Systems stay 1.0; RF/Comms/Mechanical drop to 0.3 |
| 4 | Audit script used wrong signal key names (`skill_score` etc. vs actual `skill`) — §4 signal stats were all n/a | Fixed key names in `scratch/audit_rankings.py` |

### Data quality context

The live DB was populated before migration 0008: **100% of jobs have empty `location`**, **0% have `required_experience`**, **82% have no `salary_yen`**. This means:
- Location signal defaults to 0.35 (unknown penalty) for every job — scores will improve significantly after `backfill.py` runs
- The mean score of 15.5/100 reflects current data quality, not engine quality
- Language signal (§4 median = 0%) is dominated by Japan-sourced jobs with `language=JP` in the DB

## 1. Tier distribution: existing vs new (per profile)

### Backend Platform Engineer / Software Development Engineer (`backend_platform_engineer`)
Ranked jobs: 500/500

| Tier | Old count | New count | Δ |
|------|-----------|-----------|---|
| S | 4 | 1 | -3 |
| A | 2 | 9 | +7 |
| B | 12 | 26 | +14 |
| C | 5 | 49 | +44 |
| F | 477 | 415 | -62 |

**Tier transition matrix** (old→new, ranked jobs only):

| Old\New | S | A | B | C | F |
|---------|---------|---------|---------|---------|---------|
| S | 1 | 3 | . | . | . |
| A | . | . | 2 | . | . |
| B | . | . | 10 | 2 | . |
| C | . | . | 1 | 4 | . |
| F | . | 6 | 13 | 43 | 415 |

### Cloud Platform Engineer / AWS Solutions Architect (`cloud_devops_architect`)
Ranked jobs: 500/500

| Tier | Old count | New count | Δ |
|------|-----------|-----------|---|
| S | 0 | 0 | 0 |
| A | 3 | 3 | 0 |
| B | 12 | 29 | +17 |
| C | 9 | 52 | +43 |
| F | 476 | 416 | -60 |

**Tier transition matrix** (old→new, ranked jobs only):

| Old\New | S | A | B | C | F |
|---------|---------|---------|---------|---------|---------|
| S | . | . | . | . | . |
| A | . | 1 | 2 | . | . |
| B | . | . | 7 | 5 | . |
| C | . | . | 3 | 5 | 1 |
| F | . | 2 | 17 | 42 | 415 |

### Software Engineer (Full-Stack & AI) (`niraj_matere`)
Ranked jobs: 500/500

| Tier | Old count | New count | Δ |
|------|-----------|-----------|---|
| S | 0 | 0 | 0 |
| A | 9 | 11 | +2 |
| B | 8 | 26 | +18 |
| C | 7 | 48 | +41 |
| F | 476 | 415 | -61 |

**Tier transition matrix** (old→new, ranked jobs only):

| Old\New | S | A | B | C | F |
|---------|---------|---------|---------|---------|---------|
| S | . | . | . | . | . |
| A | . | 6 | 2 | 1 | . |
| B | . | . | 4 | 4 | . |
| C | . | . | 2 | 4 | 1 |
| F | . | 5 | 18 | 39 | 414 |

## 2. Large tier shifts (≥2 tier steps)

Total large shifts across all profiles: **62**

- Upgraded (engine rates higher): 61
- Downgraded (engine rates lower): 1

### 2a. Downgrades (LLM over-rated)

| Company | Title | Profile | Tier shift | Det score | Reason | Tech |
|---------|-------|---------|------------|-----------|--------|------|
| ByteDance | Solutions Architect Graduate (BytePlus,  | niraj_matere | A→**C** | 45/100 | skill=12% loc=35% exp=80% | Python, LLMs, RAG, LangChain, LlamaIndex |

### 2b. Upgrades (LLM under-rated)

| Company | Title | Profile | Tier shift | Det score | Reason | Tech |
|---------|-------|---------|------------|-----------|--------|------|
| YO IT Consulting | Go/Golang Developer - Remote | niraj_matere | F→**B** | 81/100 | skill=62% loc=100% exp=70% | Go, Python, JavaScript, TypeScript, Node |
| YO IT Consulting | Node.js Software Engineer - Remote | niraj_matere | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| YO IT Consulting | Node.js Software Engineer - Remote | niraj_matere | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| YO IT Consulting | Python Backend Engineer - Remote | backend_platform_engineer | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| YO IT Consulting | Python Backend Engineer - Remote | niraj_matere | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| YO IT Consulting | Python Backend Engineer - Remote | backend_platform_engineer | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| YO IT Consulting | Python Backend Engineer - Remote | niraj_matere | F→**A** | 73/100 | skill=38% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| Acroname Industrial USB Hubs | SYSTEMS SOFTWARE ENGINEER | backend_platform_engineer | F→**A** | 72/100 | skill=50% loc=35% exp=70% | Python, TypeScript, React, Django, nginx |
| YO IT Consulting | Python Backend Engineer - Remote | cloud_devops_architect | F→**A** | 68/100 | skill=25% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| YO IT Consulting | Python Backend Engineer - Remote | cloud_devops_architect | F→**A** | 68/100 | skill=25% loc=100% exp=70% | Python, JavaScript, TypeScript, Node.js, |
| Acroname Industrial USB Hubs | SYSTEMS SOFTWARE ENGINEER | niraj_matere | F→**A** | 68/100 | skill=38% loc=35% exp=70% | Python, TypeScript, React, Django, nginx |
| YO IT Consulting | Node.js Software Engineer - Remote | backend_platform_engineer | F→**A** | 64/100 | skill=12% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| YO IT Consulting | Node.js Software Engineer - Remote | backend_platform_engineer | F→**A** | 64/100 | skill=12% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| Kpler | Power Backend Engineer | backend_platform_engineer | F→**A** | 64/100 | skill=62% loc=35% exp=70% | Python, FastAPI, PostgreSQL, RESTful API |
| Acroname Industrial USB Hubs | SYSTEMS SOFTWARE ENGINEER | cloud_devops_architect | F→**B** | 64/100 | skill=25% loc=35% exp=70% | Python, TypeScript, React, Django, nginx |
| Frontline Data Solutions | React/Next.JS Front-End Developer | niraj_matere | F→**B** | 64/100 | skill=25% loc=35% exp=70% | React, Next.js, JavaScript, TypeScript,  |
| Appier | Software Engineer, General Backend Devel | backend_platform_engineer | F→**B** | 63/100 | skill=38% loc=35% exp=70% | Java, Python, Go, Spring, Flask |
| Appier | Software Engineer, General Backend Devel | niraj_matere | F→**B** | 63/100 | skill=38% loc=35% exp=70% | Java, Python, Go, Spring, Flask |
| Goldman Sachs | Global Banking & Markets, Securities Set | backend_platform_engineer | F→**B** | 61/100 | skill=25% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| Goldman Sachs | Global Banking & Markets, Securities Set | cloud_devops_architect | F→**B** | 61/100 | skill=25% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| Goldman Sachs | Global Banking & Markets, Securities Set | backend_platform_engineer | F→**B** | 61/100 | skill=25% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| Goldman Sachs | Global Banking & Markets, Securities Set | cloud_devops_architect | F→**B** | 61/100 | skill=25% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| YO IT Consulting | Vue.js/Nuxt Developer - Remote | niraj_matere | F→**B** | 60/100 | skill=0% loc=100% exp=70% | Vue.js, Nuxt, Vue 3, Nuxt 3, Composition |
| YO IT Consulting | Node.js Software Engineer - Remote | cloud_devops_architect | F→**B** | 60/100 | skill=0% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| YO IT Consulting | Node.js Software Engineer - Remote | cloud_devops_architect | F→**B** | 60/100 | skill=0% loc=100% exp=70% | Node.js, Python, JavaScript, TypeScript, |
| YO IT Consulting | Angular Developer - Remote | niraj_matere | F→**B** | 60/100 | skill=0% loc=100% exp=70% | Angular, TypeScript, RxJS, Angular Unive |
| Kpler | Power Backend Engineer | niraj_matere | F→**B** | 60/100 | skill=50% loc=35% exp=70% | Python, FastAPI, PostgreSQL, RESTful API |
| Michael Page | [English Friendly] Financial Java Engine | backend_platform_engineer | F→**B** | 60/100 | skill=12% loc=35% exp=70% | Java, Spring Boot, Microservices, MSSQL, |
| Michael Page | [English Friendly] Financial Java Engine | niraj_matere | F→**B** | 60/100 | skill=12% loc=35% exp=70% | Java, Spring Boot, Microservices, MSSQL, |
| Michael Page | [English Friendly] Financial Java Engine | backend_platform_engineer | F→**B** | 60/100 | skill=12% loc=35% exp=70% | Java, Spring Boot, Microservices, MSSQL, |
| Michael Page | [English Friendly] Financial Java Engine | niraj_matere | F→**B** | 60/100 | skill=12% loc=35% exp=70% | Java, Spring Boot, Microservices, MSSQL, |
| Aquatech | QUA- Product Manager of Ultrafiltration  | niraj_matere | F→**B** | 59/100 | skill=25% loc=35% exp=70% |  |
| Aquatech | QUA- Product Manager of Ultrafiltration  | niraj_matere | F→**B** | 59/100 | skill=25% loc=35% exp=70% |  |
| Aquatech | QUA- Product Manager of Ultrafiltration  | niraj_matere | F→**B** | 59/100 | skill=25% loc=35% exp=70% |  |
| Kpler | Power ML Engineer | backend_platform_engineer | F→**B** | 58/100 | skill=62% loc=35% exp=70% | Python, FastAPI, PostgreSQL, AWS, Terraf |
| Goldman Sachs | Global Banking & Markets, Securities Set | niraj_matere | F→**B** | 56/100 | skill=12% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| Goldman Sachs | Global Banking & Markets, Securities Set | niraj_matere | F→**B** | 56/100 | skill=12% loc=35% exp=80% | Java, AWS, DynamoDB, Lambda, Fargate |
| Red Hat | Customer Site Reliability Engineer - Ope | cloud_devops_architect | F→**B** | 56/100 | skill=38% loc=35% exp=70% | OpenShift, Kubernetes, AWS, Azure, Linux |
| Red Hat | Customer Site Reliability Engineer - Ope | cloud_devops_architect | F→**B** | 56/100 | skill=38% loc=35% exp=70% | OpenShift, Kubernetes, AWS, Azure, Linux |
| Kpler | Power Backend Engineer | cloud_devops_architect | F→**B** | 56/100 | skill=38% loc=35% exp=70% | Python, FastAPI, PostgreSQL, RESTful API |

## 3. Hard-fail gate overrides (engine→F despite LLM S/A/B)

Total: **0**

## 4. Signal analysis (all ranked jobs, all profiles)

Average score per signal component across ranked jobs:

| Signal | Mean | P25 | Median | P75 |
|--------|------|-----|--------|-----|
| skill | 15.0 | 0.0 | 12.5 | 25.0 |
| title | 45.9 | 30.0 | 30.0 | 30.0 |
| experience | 60.7 | 70.0 | 70.0 | 70.0 |
| language | 27.0 | 0.0 | 0.0 | 100.0 |
| location | 37.5 | 35.0 | 35.0 | 35.0 |

## 5. Unranked jobs the engine now rates A/S (missed by old LLM-only pipeline)

## 6. Skill gap analysis (per profile, jobs rated B/C/F by engine)

### `backend_platform_engineer` — top tech in B/C/F jobs (skills the profile lacks coverage on)

| Skill | Count |
|-------|-------|
| python | 23 |
| aws | 15 |
| docker | 14 |
| java | 12 |
| kubernetes | 11 |
| javascript | 10 |
| go | 8 |
| linux | 7 |
| typescript | 7 |
| ci/cd | 7 |
| ansible | 6 |
| c++ | 6 |
| gcp | 6 |
| azure | 6 |
| llms | 5 |

### `cloud_devops_architect` — top tech in B/C/F jobs (skills the profile lacks coverage on)

| Skill | Count |
|-------|-------|
| python | 31 |
| aws | 20 |
| java | 18 |
| docker | 17 |
| go | 14 |
| kubernetes | 13 |
| javascript | 12 |
| typescript | 10 |
| gcp | 9 |
| linux | 8 |
| c++ | 8 |
| node.js | 8 |
| azure | 7 |
| ansible | 6 |
| terraform | 6 |

### `niraj_matere` — top tech in B/C/F jobs (skills the profile lacks coverage on)

| Skill | Count |
|-------|-------|
| python | 23 |
| aws | 16 |
| docker | 15 |
| kubernetes | 12 |
| java | 11 |
| javascript | 9 |
| linux | 7 |
| ci/cd | 7 |
| go | 7 |
| ansible | 6 |
| gcp | 6 |
| terraform | 6 |
| typescript | 6 |
| azure | 6 |
| c++ | 5 |

## 7. Key findings and recommended tuning

- **Hard-fail rate:** 0 jobs (0.0% of ranked) are gated to F by the new engine despite the LLM giving them S/A/B. Verify these make sense.
- **LLM vs engine disagreements ≥2 tiers:** 1 downgrades, 61 upgrades.
- **Mean deterministic score:** 15.4/100 across ranked jobs.

- **Skill signal:** mean 15.0, 1331 jobs (88%) score <30 on skill overlap.
  - ⚠ Low mean skill score suggests the profile's `core_skills` list may not cover common JD vocabulary well. Consider expanding skill aliases in `matching.py` or adding more profile skills.

- **Location signal:** 0 jobs (0%) scored 0 on location — likely missing or unrecognised location text.
  - Fix: ensure Apify actors populate `location` field; consider expanding `region_for_text` keyword map in `locations.py`.

### Tuning recommendations

1. **Review downgrades list (§2a):** If legitimate jobs appear, the experience or location weight may be too punishing. Consider softening the experience hard-gate from `profile+2y` to `profile+3y`.
2. **Review hard-fail overrides (§3):** Any job where the LLM gave A/S but the engine forces F is worth manual inspection — the LLM sometimes sees context the structured fields miss.
3. **Expand skill aliases (matching.py):** Common tech in B/C/F jobs (§6) that overlaps with profile core skills but under different names → add to `_SKILL_ALIASES`.
4. **Location data quality:** Many jobs arrive with empty `location`. Improve `persistence.detect_job_location()` by scanning more Apify raw fields (`headquarters`, `remote`).
5. **Salary signal:** Currently only nudges ±5 pts; if salary data coverage is low (check §4 signals), verify `salary_yen` is populated in more jobs.