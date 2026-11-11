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
