# Decision Log

Append new entries at the bottom: `ADR-NNN: title`, date, status, context, decision, consequences. When a decision is replaced, mark it superseded instead of deleting it.

## ADR-001: Python + FastAPI backend, vanilla HTML/CSS/JS frontend
- **Date:** 2026-11-11, **Status:** accepted (amended by ADR-007)
- **Decision:** FastAPI serves the API (SSE) and the static frontend. No frontend framework and no build step.

## ADR-002: Own streaming agent loop
- **Date:** 2026-11-11, **Status:** accepted (amended by ADR-008: the loop targets OpenAI-compatible chat-completions)
- **Context:** The UI needs streamed text, live tool-progress chips, and UI blocks pushed mid-turn.
- **Decision:** A hand-written loop in `app/agent/loop.py`.

## ADR-003: Server-side hydration of UI blocks
- **Date:** 2026-11-11, **Status:** accepted
- **Decision:** `render_view` takes IDs and a template name. The server builds the block from the DB, so the LLM never transcribes the numbers shown.

## ADR-004: Deterministic, explainable scoring
- **Date:** 2026-11-11, **Status:** accepted
- **Decision:** `services/scoring.py` ranks candidates with a per-criterion breakdown. The LLM explains results and tunes weights.

## ADR-005: SQLite for development
- **Date:** 2026-11-11, **Status:** superseded by ADR-006

## ADR-006: SQL Server with the user-supplied fixed schema, accessed through pyodbc
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** The user requires MS SQL Server (local instance for dev) and a fixed table structure.
- **Decision:** pyodbc with ODBC Driver 17 for SQL Server and parameterized SQL in a single repository module. No ORM and no migrations, because the app never runs DDL. The app writes only to `AgentMemory`.
- **Consequences:** Fewer wheels. The ODBC driver is an MSI prerequisite on the server. No Job table exists, so JDs come from documents or pasted text (see TOOLS.md, `extract_job_spec`).

## ADR-007: Air-gapped deployment standard
- **Date:** 2026-11-11, **Status:** accepted
- **Decision:** Follow `docs/AIRGAP_DEPLOYMENT_STANDARD.md`: wheels only in `wheels/`, `usb_x_y_z` releases, a `PRODUCTION` switch in `.env`, no CDN (Chart.js vendored), and HTTPS with the org certificate in prod.

## ADR-008: OpenAI-compatible LLM client with capability fallbacks
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** The production server is air-gapped. The only LLM there is the corporate MaaS gateway, which is OpenAI-compatible (the sibling project uses `deepseek-v41-flash`). A public LLM API cannot be reached.
- **Decision:** One OpenAI-compatible chat-completions client (`httpx` + `truststore`) for dev and prod, configured only through `.env`. Native function calling is preferred. If the gateway doesn't support it, a prompted-JSON tool mode takes over.
- **Consequences:** The dev endpoint is interchangeable. Gateway support for tools and streaming must be verified on the server (see ROADMAP).

## ADR-009: Adopt the server tables (T_IIR_ARIF_*) and an app-owned memory table
- **Date:** 2026-11-11, **Status:** accepted (partly supersedes ADR-006: `AgentMemory` no longer exists)
- **Context:** The user supplied the production table structure (`docs/schema/db_structure_server.txt`). It has no FK constraints; child tables carry both `ARIF_ID` and the ATS `CANDIDATE_ID`. There is no table for chat state, and the user allowed the app to create its own tables.
- **Decision:** The dev DB recreates the four `T_IIR_ARIF_*` tables exactly (`sql/01_dev_server_tables.sql`) with fake data (`scripts/seed_dev_db.py`); the old dev tables were dropped. The app's `candidate_id` is `ARIF_ID` (the PK). Chat state moves to `T_IIR_ARIF_AGENT_MEMORY` (`sql/02_agent_memory.sql`), created by a DBA, never by the app at runtime, so the app login needs no DDL rights. If that table is missing, the app keeps state in process memory and reports it in `/api/health`.
- **Consequences:** Code developed on dev runs unchanged on the server. Releases exclude the dev-only DDL and the seed script. The skill vocabulary is `DISTINCT NORM_SKILL` (cached for 5 minutes).

## ADR-010: SAUDI_EXPAT is a requisition hard filter, never a score
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** CLAUDE.md rule 5 requires a decision before any compliance-driven criterion. The user confirmed that requisitions are specifically for a local (Saudi) or an expat hire, and that `SAUDI_EXPAT` holds `Saudi` or `Expat`.
- **Decision:** `hire_type` is part of the JobSpec (taken from the JD, e.g. "Hire type: Saudi", or set by the recruiter) and is applied only as a pool filter in SQL. It never contributes to a score, ranking order or prompt reasoning: identical job-related profiles get identical scores. Explicitly requested candidates who don't match are scored but flagged `hire_type_mismatch`. `GENDER` and `NATIONAL_ID` are never selected, and `COUNTRY` is display only until Q4 is answered.
- **Consequences:** The prompt allows exactly this one exception to "never filter by nationality". Tests assert that the score is independent of hire type.

## ADR-011: Assessments replace certifications as the fifth scoring criterion
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** The server has no certifications data. It has inductive (`INDREASON`), numerical (`NUMREASON`) and verbal (`VERBREASON`) reasoning scores, 0–100, stored as text.
- **Decision:** The `assessments` criterion (default weight 0.10) is the mean of the available scores / 100. With no scores on file it is 0.5 (neutral), with a `no_assessment` flag, so missing data is neither a penalty nor a bonus. Recruiters can change the weight, including to 0.
- **Consequences:** Default weights: skills 0.40, experience 0.25, relevance 0.15, education 0.10, assessments 0.10. Saved specs that still carry `certifications` load fine; the key is ignored.

## ADR-012: Original columns only; skills grouped in Python
- **Date:** 2026-11-11, **Status:** accepted (amends ADR-009)
- **Context:** The user said the `NORM_*` columns are no longer used. Raw `ORG_SKILL` values have many spellings ("Excel", "MS Excel", "Advanced Excel", Arabic).
- **Decision:** The app reads only the original columns. The skill vocabulary is the distinct `ORG_SKILL` values grouped by `normalize.canonical` (case, punctuation, alias map including Arabic synonyms). The display name is the plain, capitalised spelling. SQL filters list every stored spelling of a skill and compare against the raw column, so it stays sargable. Degree level is derived from the `DEGREE` text with matching SQL and Python patterns. Free-text dates are parsed in Python, only for ordering. The dev seed leaves every `NORM_*` column NULL.
- **Consequences:** Grouping quality depends on `normalize.ALIASES`, which is the single place to add synonyms. `COUNTRY` is confirmed to be nationality and is never selected.

## ADR-013: Application status reference file
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** The server has 60+ `APPLICATION_STATUS_CODE` values. The user maintains a list of their order and of whether candidates in each status should be considered.
- **Decision:** `data/reference/application_statuses.csv` (`code, status, stage, stage_order, include_in_matching`) is loaded at startup. Codes with `include_in_matching=N` are excluded from `match_candidates` pools by default, and `include_all_statuses` overrides that. Codes missing from the file count as included. `status_mix` and `stage_mix` follow the file's order. The file is a placeholder until the user supplies the real list.
- **Consequences:** Changing the list needs no code change, only a restart. Candidates passed explicitly by id with an excluded status are scored but flagged `status_not_open`.

## ADR-014: Query design for 350k–500k candidates
- **Date:** 2026-11-11, **Status:** accepted
- **Context:** The production volume is 350k–500k candidates, with several million child rows. The server tables have no known indexes beyond the identity PKs, and we may not alter them.
- **Decision:** Pools are pre-filtered and capped in SQL. Searches use set-based `IN (subquery)` and never an `OR` across tables, which took 128 s at 100k rows against 0.9 s after the rewrite. The count comes from `COUNT(*) OVER ()` in the same query. Profiles for more than 500 ids load through a session temp table, so each child table is scanned once. The skill vocabulary is cached for 10 minutes. `sql/03_recommended_indexes.sql` is offered to the table owner as a request.
- **Consequences:** Measured at 100k rows without indexes: matching about 1 s, every search under 1 s. Re-time with the scale-up method after changing a query (clone the dev rows in SQL, then reseed).

## ADR-015: Profile side panel, hydrated without the LLM
- **Date:** 2026-11-13, **Status:** accepted
- **Context:** Opening a profile sent a chat prompt. Each profile cost a model round trip (seconds, tokens), landed at the bottom of the chat, and the recruiter had to scroll back up to the ranking to open the next one.
- **Decision:** A read-only endpoint, `GET /api/candidates/{id}/profile?chat_id=`, returns the existing `candidate_profile` block. `render.build` hydrates it from the DB and scores it against the chat's active job spec (reloaded from agent memory if needed), so the numbers match the ranking. The frontend shows it in a side panel with previous/next through the list it was opened from. It does not call the LLM, change chat history or write to memory. The audit log records `profile_view` with metadata only. "Ask about this candidate" is the explicit hand-over to the chat.
- **Consequences:** The model does not see which profiles a recruiter looked at unless they ask about one. Core rule 3 still holds: the UI shows only server-hydrated data. Frontend logic is unit-tested with Node's test runner and a fake DOM (dev-only, no new dependency, nothing shipped).
