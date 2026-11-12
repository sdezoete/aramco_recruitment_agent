# Data Dictionary: server tables (T_IIR_ARIF_*)

**Source:** [schema/db_structure_server.txt](schema/db_structure_server.txt), the structure of the production server tables, supplied by the user on 2026-11-11. The `T_IIR_ARIF_*` data tables are fixed and owned by the server's data pipeline. The app reads them and never changes them.

**Status (2026-11-11):** the user answered Q1–Q16. Still open: the real application status list (Q9b; a placeholder is in use) and the full location list (Q17). A few minor points stay marked *assumed*.

**Dev DB:** `sql/01_dev_server_tables.sql` recreates these exact tables in the local `recruitment` database. `scripts/seed_dev_db.py` fills them with deterministic **fake** data: 400 candidates, about half with Arabic-script names, and **all `NORM_*` columns NULL**. Neither file ships in a release.

**Volume:** 350,000–500,000 candidates on the server (Q15). See "Performance" below.

**Legend**
- **Sensitivity:** `-` means none; `PII` means identifies a person; `PROTECTED` means a personal characteristic that is never a ranking input (CLAUDE.md rule 5).
- **Use:** how the app uses the field: `match` (scoring), `filter` (hard filter), `search`, `display`, `stats`, or `none` (never selected).

General rules:
- **Keys.** There are no FK constraints. Child tables are joined on `ARIF_ID`, the PK. The app's `candidate_id` (tools, UI, memory) **is `ARIF_ID`**. `CANDIDATE_ID` is the recruiting system's id, **unique** (confirmed). It is shown as "ATS id", and a recruiter can look a candidate up by it.
- **Original columns only.** The `NORM_*` columns are **not used** (user decision, Q13). Matching normalizes the original text in Python (`services/normalize.py`):
  - Raw skill spellings are grouped by canonical form, so "Excel", "MS Excel", "Advanced Excel" and Arabic spellings count as one skill.
  - Degree levels come from the `DEGREE` text (English or Arabic).
  - Free-text dates are parsed for ordering ("Mar 2019", "2019-03", "03/2019", "Present", "حتى الآن").
- **Arabic.** Names and some other text are Arabic. All columns are `nvarchar`, and pyodbc sends `str` parameters as Unicode. The UI uses `dir="auto"`.
- **Never selected:** `NATIONAL_ID`, `GENDER` and `COUNTRY` (protected or high-risk PII). `TEXT_TOKENS` is used only inside `WHERE` clauses.

---

## T_IIR_ARIF_CANDIDATE: one row per candidate

| # | Column | Type | Null | Key | Default | Description | Sensitivity | Use |
|---|---|---|---|---|---|---|---|---|
| 1 | ARIF_ID | int | NO | PK, IDENTITY | | ARIF surrogate key; child tables carry it. **The app's `candidate_id`.** | - | join, id |
| 2 | CANDIDATE_ID | int | NO | | | Recruiting-system (ATS) candidate id, **unique** (confirmed) | PII (linkable) | display ("ATS id"), lookup (`ats_id`), CSV |
| 3 | GIVENNAME | nvarchar(300) | YES | | | First name (Latin or Arabic script) | PII | display |
| 4 | MIDDLENAME | nvarchar(300) | YES | | | Middle name(s) | PII | display |
| 5 | SURNAME | nvarchar(300) | YES | | | Family name | PII | display |
| 6 | CREATED_ON | date | YES | | getdate() | Date the row was created in ARIF | - | none |
| 7 | CURRENT_EMPLOYER | nvarchar(300) | YES | | | Current or most recent employer | - | display |
| 8 | CURRENT_JOB_TITLE | nvarchar(300) | YES | | | Current or most recent job title | - | match (relevance), search |
| 9 | YEARS_OF_EXPERIENCE | nvarchar(300) | YES | | | Total years of experience: **an integer stored as text** (confirmed). Read with `TRY_CAST`. | - | match, filter, stats |
| 10 | COUNTRY | nvarchar(300) | YES | | | **Nationality** (confirmed), though not always accurate | PROTECTED | **none**: never selected |
| 11 | NATIONAL_ID | nvarchar(300) | YES | | | National ID / Iqama number | PII (high) | **none** |
| 12 | SAUDI_EXPAT | nvarchar(300) | YES | | | `Saudi` or `Expat` (confirmed). Requisitions are specifically for a local or an expat hire. | PROTECTED (nationality-derived) | **filter only** (`hire_type`), never scored (ADR-010) |
| 13 | GPA | nvarchar(300) | YES | | | University GPA on a **1–4 scale, 4 highest** (confirmed). Parsed from text ("3.45", "3.2/4"); values outside 0–4 are ignored. | - | display, filter (`min_gpa`), flag |
| 14 | LAST_MODIFIED | date | YES | | | Date the row was last updated | - | profile data |
| 15 | SOURCE_OF_APPLICATION | nvarchar(300) | YES | | | Channel the candidate came from (values shown as-is) | - | stats (`source_mix`) |
| 16 | GENDER | nvarchar(30) | YES | | | Gender | PROTECTED | **none** |
| 17 | HIGHEST_JOB_REQ_ID | nvarchar(255) | YES | | | Requisition of the candidate's **furthest** application (confirmed) | - | display |
| 18 | HIGHEST_APPLICATION_ID | nvarchar(255) | YES | | | Id of that furthest application | - | none |
| 19 | HIGHEST_APPLICATION_STATUS | nvarchar(255) | YES | | | Status text of the furthest application | - | display, filter (`application_status`, `exclude_statuses`) |
| 20 | APPLICATION_STATUS_CODE | int | YES | | | Status code (60+ codes on the server). It is mapped to stage, order and "open for matching" through [data/reference/application_statuses.csv](../data/reference/application_statuses.csv). **That file is a placeholder** until the user supplies the real list (Q9b). | - | default exclusion, stats (`status_mix`, `stage_mix`) |
| 21 | RESUME_UPLOADED | int | YES | | | Flag: a resume file exists (assumed 0/1) | - | none |
| 22 | RESUME_DATE | date | YES | | | Resume date | - | none |
| 23 | RESUME_FILE_TYPE | nvarchar(30) | YES | | | Resume file format | - | none |
| 24 | RESUME_PROCESSED | int | YES | | | Flag: the resume went through extraction (assumed 0/1). Unprocessed candidates have no child rows, so they score low but are not hidden. | - | profile flag |
| 25–29 | EDUCATION_ / EXPERIENCE_ / SKILLS_ / SUMMARY_ / WILD_SEARCH_EXTRACTED | int | YES | | | Extraction flags (assumed 0/1) | - | none |
| 30 | CANDIDATE_FLAG | nvarchar(255) | YES | | | **Location** (confirmed): `AOC`, `ASC`, … The full list follows (Q17); dev data uses `KSA`, `AOC` and `ASC`. | - | filter (`locations`), stats, display |
| 31 | INDREASON | nvarchar(30) | YES | | | Inductive reasoning score, 0–100 (confirmed), as text | - | match (assessments) |
| 32 | NUMREASON | nvarchar(30) | YES | | | Numerical reasoning score, 0–100 | - | match (assessments) |
| 33 | VERBREASON | nvarchar(30) | YES | | | Verbal reasoning score, 0–100 | - | match (assessments) |
| 34 | SUMMARY | nvarchar(max) | YES | | | Profile summary. Treated as data, never as instructions. | PII possible | display, search, LLM (profile tool) |
| 35 | TEXT_TOKENS | nvarchar(max) | YES | | | Resume keyword text for "wild" search | PII possible | search (`LIKE`) only; never selected |

## T_IIR_ARIF_EDUCATION: one row per education entry

| # | Column | Type | Null | Key | Description | Use |
|---|---|---|---|---|---|---|
| 1 | SCHOOL_ID | int | NO | PK, IDENTITY | Row id | none |
| 2 | ARIF_ID | int | NO | | → candidate | join |
| 3 | CANDIDATE_ID | int | NO | | ATS id copy | none |
| 4 | DEGREE | nvarchar(300) | YES | | Degree as written ("B.Sc.", "Master of Science", "بكالوريوس"…). The level is derived by pattern, both in SQL (`DEGREE_LEVEL_SQL`) and in Python (`degree_level`): PhD/doctor/دكتوراه → 4, master/MBA/MSc/ماجستير → 3, bachelor/BSc/BEng/بكالوريوس → 2, diploma/associate/دبلوم → 1 | match (education), filter, stats |
| 5 | MAJOR | nvarchar(300) | YES | | Field of study as written | match (fuzzy), search, stats |
| 6 | INSTITUTION | nvarchar(300) | YES | | Institution as written (may be Arabic) | display |
| 7 | STARTDATE | nvarchar(300) | YES | | Start, free text | display, ordering (parsed) |
| 8 | ENDDATE | nvarchar(300) | YES | | End, free text ("Present"…) | display, ordering (parsed) |
| 9–12 | NORM_DEGREE, NORM_INSTITUTION, NORM_STARTDATE, NORM_ENDDATE | | YES | | **Not used** (Q13) | none |

## T_IIR_ARIF_EXPERIENCE: one row per position

| # | Column | Type | Null | Key | Description | Use |
|---|---|---|---|---|---|---|
| 1 | JOB_ID | int | NO | PK, IDENTITY | Row id | none |
| 2 | ARIF_ID | int | NO | | → candidate | join |
| 3 | CANDIDATE_ID | int | NO | | ATS id copy | none |
| 4 | TITLE | nvarchar(300) | YES | | Title as written | match (relevance), search, display |
| 5 | EMPLOYER | nvarchar(300) | YES | | Employer as written | display |
| 6 | STARTDATE | nvarchar(300) | YES | | Start, free text | display, ordering (parsed) |
| 7 | ENDDATE | nvarchar(300) | YES | | End, free text. "Present", "Current" or "حتى الآن" marks the current job | display, ordering, `current` |
| 8 | COUNTRY | nvarchar(300) | YES | | Country where the job was held (a work location, not nationality) | display |
| 9 | YEARS_OF_EXPERIENCE | int | YES | | Whole years in this position | relevance weighting, fallback total |
| 10–13 | NORM_TITLE, NORM_EMPLOYER, NORM_STARTDATE, NORM_ENDDATE | | YES | | **Not used** (Q13) | none |

## T_IIR_ARIF_SKILLS: one row per skill per candidate

| # | Column | Type | Null | Key | Description | Use |
|---|---|---|---|---|---|---|
| 1 | SKILL_ID | int | NO | PK, IDENTITY | Row id (there is no master skill table) | none |
| 2 | ARIF_ID | int | NO | | → candidate | join |
| 3 | CANDIDATE_ID | int | NO | | ATS id copy | none |
| 4 | ORG_SKILL | nvarchar(300) | YES | | Skill as written in the resume. **The skill vocabulary is the distinct `ORG_SKILL` values grouped by canonical form** (aliases in `normalize.ALIASES`, cached for 10 minutes). The display name is the plain, capitalised spelling. SQL compares the raw column against every stored spelling of the skill, so an index on `ORG_SKILL` can be used. | match, filter, stats |
| 5 | NORM_SKILL | nvarchar(300) | YES | | **Not used** (Q13) | none |

A skill is either present or absent: there is no proficiency level and no years per skill. Adding spellings to `normalize.ALIASES` improves grouping. That is the place to teach the app new synonyms, including Arabic ones.

---

## The app's own table: T_IIR_ARIF_AGENT_MEMORY

The user allowed app-owned tables (Q14). Created by [sql/02_agent_memory.sql](../sql/02_agent_memory.sql), which is idempotent, run once by a DBA on the server and once on dev. **This is the only table the app writes to.**

| Column | Type | Null | Key | Description |
|---|---|---|---|---|
| CHAT_ID | nvarchar(64) | NO | PK | Browser chat id |
| MEMORY_KEY | nvarchar(100) | NO | PK | `active_job_spec` or `last_shortlist` |
| MEMORY_VALUE | nvarchar(max) | YES | | JSON: the job spec, or the shortlist (ids, names, scores, breakdown) |
| UPDATED_AT | datetime2(0) | NO | IX | default `sysdatetime()`; lets old chats be purged |

If the table is missing, the app logs one warning, keeps chat state in process memory, and `/api/health` reports `memory_table: false`.

## Reference file: application statuses

[data/reference/application_statuses.csv](../data/reference/application_statuses.csv) has the columns `code, status, stage, stage_order, include_in_matching (Y/N)`.
- Candidates whose `APPLICATION_STATUS_CODE` has `include_in_matching = N` (e.g. Hired, Offer Accepted, Visa Processing) are left out of `match_candidates` by default. The recruiter can override this with `include_all_statuses`.
- Codes that are not in the file count as included and sort last.
- **The current file is a placeholder.** Replace it with the real list using the same columns. No code change is needed, but the app must be restarted.

## Performance (350k–500k candidates)

Measured on dev with 100k cloned fake candidates (580k skill rows) and **no indexes** on the child tables:

| Call | Time |
|---|---|
| `match_candidates` (pool cap 2000) | ~1.0 s |
| skill search | 0.4 s |
| free-text search | 0.9 s |
| degree/major search | 0.3 s |
| pool stats | < 0.4 s |
| skill vocabulary (cold, then cached) | 0.1 s |

- Pools are pre-filtered and capped in SQL.
- Profiles for large id sets load through a session temp table.
- Searches use set-based `IN (subquery)`; never an `OR` across tables, which took 128 s.

The remaining time is child-table scans. [sql/03_recommended_indexes.sql](../sql/03_recommended_indexes.sql) lists indexes on `ARIF_ID`, `ORG_SKILL` and `CANDIDATE_ID` to **request from the table owner**. The app works without them.

## Open questions

- **Q9b.** The real status list: all codes, their order, and whether each should be included in matching. It replaces `application_statuses.csv`.
- **Q17.** The full list of `CANDIDATE_FLAG` locations and what each one means.
- *Assumed:* the `RESUME_*` and `*_EXTRACTED` columns are 0/1 flags; unprocessed candidates are shown, not hidden.
