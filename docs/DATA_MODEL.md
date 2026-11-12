# Data Model

**Tables:** see [DATA_DICTIONARY.md](DATA_DICTIONARY.md), which is authoritative. The app reads the server's `T_IIR_ARIF_*` tables (read-only, structure fixed) and writes only to its own `T_IIR_ARIF_AGENT_MEMORY`. Never alter the `T_IIR_ARIF_*` data tables. New app-owned tables need a script in `sql/` and a DECISIONS entry.

- Engine: Microsoft SQL Server. Dev: SQL Server 2022 Developer at `localhost`, database `recruitment`, Windows auth, ODBC Driver 17. The dev DB holds an exact copy of the server tables (`sql/01_dev_server_tables.sql`) with fake data (`scripts/seed_dev_db.py`).
- Access: `pyodbc`, with parameterized SQL in `app/db/repository.py` only.

## Candidate profile (what the repository returns)

`Repository.profiles(ids)` assembles one dict per candidate from the four tables. Tools, scoring and rendering use only this shape, never raw columns.

| key | source |
|---|---|
| `candidate_id` | `ARIF_ID` |
| `ats_id` | `CANDIDATE_ID` (unique; `get_candidate_profile` accepts it) |
| `full_name` | `GIVENNAME MIDDLENAME SURNAME` (may be Arabic) |
| `last_job_title`, `last_company` | `CURRENT_JOB_TITLE`, `CURRENT_EMPLOYER` |
| `total_experience` | `YEARS_OF_EXPERIENCE` parsed as a number; falls back to the sum of the experience rows |
| `location` | `CANDIDATE_FLAG` (AOC, ASC, …) |
| `hire_type` | `SAUDI_EXPAT` (`Saudi` / `Expat`), used only as a filter |
| `gpa` | `GPA` parsed as a number on the 1–4 scale (null when out of range) |
| `source`, `application_status`, `status_code`, `job_req_id` | `SOURCE_OF_APPLICATION`, `HIGHEST_APPLICATION_STATUS`, `APPLICATION_STATUS_CODE`, `HIGHEST_JOB_REQ_ID` |
| `pipeline_stage`, `status_included` | from `data/reference/application_statuses.csv` by status code |
| `assessments` | `{inductive: INDREASON, numerical: NUMREASON, verbal: VERBREASON}`, each 0–100 or null |
| `summary` | `SUMMARY` |
| `skills[]` | `ORG_SKILL` grouped by canonical form, shown with the vocabulary's display spelling |
| `experience[]` | `{job_title, company, location (work country), years_experience, start, end, current}` (original columns), current job first, then by parsed date |
| `education[]` | `{degree, level (0–4, from the DEGREE text), major, institute, start, end}`, newest first |
| `highest_degree`, `primary_major` | the education row with the highest level |

Never in a profile: `NATIONAL_ID`, `GENDER`, `COUNTRY` (nationality), `TEXT_TOKENS`, or any `NORM_*` column (not used, ADR-012).

## Scoring model (`services/scoring.py`)

A **JobSpec** holds `title`, `required_skills[]`, `preferred_skills[]`, `min_years`, `degree_level`, `min_gpa` (1–4; below it adds a `below_min_gpa` flag, not an exclusion), `majors[]`, `title_keywords[]`, `weights`, and two **hard filters**: `hire_type` (Saudi / Expat / none) and `locations[]`.

**Hard filters run first.** Hire type, location, the statuses marked not open for matching in `application_statuses.csv` (unless `include_all_statuses`), and the optional `exclude_statuses` are applied in SQL when building the pool. They never contribute to a score: two candidates with the same job-related profile get the same score, whatever their hire type (ADR-010). Candidates passed explicitly by id are still scored and get a `hire_type_mismatch` / `location_mismatch` flag.

| criterion | default weight | computation (each scored 0–1) |
|---|---:|---|
| skills | 0.40 | matched required skills / required count (canonical match against `ORG_SKILL`), plus a bonus of up to 0.1 for preferred skills, capped at 1 |
| experience | 0.25 | `min(total_experience / min_years, 1.0)`; 1.0 when `min_years` is 0 (0.5 when the candidate has no experience) |
| relevance | 0.15 | overlap of title keywords with the current title and with `TITLE` of each position, weighted by its years |
| education | 0.10 | degree level from `DEGREE` meets the requirement (one level below scores 0.5), plus a fuzzy major match on `MAJOR` |
| assessments | 0.10 | mean of the available reasoning scores / 100. **None on file → 0.5 (neutral)** with a `no_assessment` flag |

- Names are normalized for matching: Unicode-aware case folding and punctuation stripping, plus a small alias map (for example "ms excel" → "excel"). Arabic text survives normalization.
- A missing must-have skill adds a `missing_must_have` flag; the candidate is not excluded.
- Weights can be overridden through tool arguments and are normalized to sum to 1. Unknown keys (such as `certifications` from older saved specs) are ignored.
- Output always includes the breakdown, `matched_skills`, `missing_skills` and `flags`.

## Pool selection (`match_candidates`)

The pool is the candidates that have any spec skill and pass the hard filters, capped at `MATCH_MAX_POOL` (2000) in SQL and ordered by the number of matching skills, then years of experience. At 350k–500k candidates the pool is never loaded unfiltered (performance notes in DATA_DICTIONARY.md). When fewer than 50 match, all eligible candidates (up to the cap) are scored too, so near-misses still show.
