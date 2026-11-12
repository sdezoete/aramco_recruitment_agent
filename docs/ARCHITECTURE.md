# Architecture

## Overview

```
 Browser (vanilla JS, no CDN)            FastAPI backend (HTTPS in prod)          LLM (OpenAI-compatible)
 ┌──────────────────────┐   POST /api/chat   ┌───────────────────────────┐ /chat/completions ┌──────────────────┐
 │ chat input           │ ─────────────────► │ agent/loop.py             │ ────────────────► │ dev: any endpoint │
 │ message stream       │ ◄───── SSE ─────── │  - stream text deltas     │ ◄──────────────── │ prod: MaaS gateway│
 │ UI block renderers   │                    │  - run tools (registry)   │                   └──────────────────┘
 │ Chart.js (vendored)  │                    │  - emit ui_block events   │
 └──────────────────────┘                    └────────────┬──────────────┘
                                                          │
                                     tools/ ── services/scoring.py
                                                          │
                                     db/repository.py ── pyodbc ── SQL Server (recruitment)
                                                          │
                                     data/docs/ (JDs, reference docs)
```

## Request flow (one chat turn)

1. The browser POSTs `{chat_id, message}` to `/api/chat` and reads the response as an SSE stream.
2. `agent/loop.py` loads the chat history (in process memory) and the chat's state from `T_IIR_ARIF_AGENT_MEMORY` (`active_job_spec`, `last_shortlist`), then calls the LLM with the system prompt, history and tool definitions, using `stream=true` and `tool_choice=auto`.
3. Content deltas are forwarded to the browser as `text_delta` events.
4. When `finish_reason == "tool_calls"`, the loop:
   - emits `tool_start` for each call (the UI shows a "Searching candidates…" chip)
   - parses the arguments with `json.loads`, validates them against the schema, and runs the handler
   - for `render_view`, hydrates the block and emits `ui_block`
   - appends the assistant message (with its `tool_calls`) and one `role: tool` message per call, then loops
5. On `stop`, the loop emits `done`. On `length`, or after `AGENT_MAX_STEPS`, it emits `done` with a note. Errors emit `error` with a user-safe message (no stack traces when `PRODUCTION=True`).

## SSE event protocol

| event        | data |
|--------------|------|
| `text_delta` | `{ "text": "..." }` |
| `tool_start` | `{ "id", "name", "label" }` |
| `tool_end`   | `{ "id", "ok", "summary" }` |
| `ui_block`   | a UI block (RESPONSE_TEMPLATES.md) |
| `done`       | `{ "steps", "note"? }` |
| `error`      | `{ "message" }` |

## LLM client (`app/llm/client.py`)

- Uses `httpx` with `truststore`, so the internal CA in the Windows store is trusted. `LLM_CA_FILE` is an optional extra CA, and `LLM_VERIFY_SSL` is forced on when `PRODUCTION=True`. Proxy environment variables are ignored by default (`trust_env=False`).
- **Capability probe** at startup and through `/api/health`: `GET /models` checks reachability and that the model id exists; a small `tools` request checks native function calling; a small `stream` request checks streaming. The results are cached in memory.
- Fallbacks:
  - no native tools: prompted-JSON tool mode (TOOLS.md)
  - no streaming: non-streaming request; the full text is sent as a single `text_delta`
  - `response_format` rejected: retried without it
- Retries: `LLM_MAX_RETRIES` with backoff on 429, 5xx and connection errors. No retry on 400 or 401.

## Data access

- `db/connection.py` builds the ODBC connection string from `DB_*`: `DB_DRIVER`, `DB_SERVER`, `DB_NAME`, `DB_TRUSTED_CONNECTION`, or `DB_USER`/`DB_PASSWORD`, plus `DB_ENCRYPT` and `DB_TRUST_SERVER_CERTIFICATE`.
- One connection per request, from a small pool, with autocommit on for reads. Writes are limited to `T_IIR_ARIF_AGENT_MEMORY`; the `T_IIR_ARIF_*` data tables are read-only.
- All SQL lives in `db/repository.py` and is parameterized.

## Configuration (`.env`, read by `app/config.py`)

Order: built-in defaults → `.env` → `RA_<KEY>` environment variables (used by tests and the mock LLM). See `.env.example` for every key. `PRODUCTION=True` enforces the rules in AIRGAP_DEPLOYMENT_STANDARD §4.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | static frontend |
| GET | `/api/health` | version, PRODUCTION flag, DB reachable, LLM reachable and capabilities |
| POST | `/api/chat` | SSE chat turn |
| POST | `/api/upload-jd` | upload JD text, .docx or .pdf. Returns text the chat can use |
| GET | `/api/export/shortlist.csv?chat_id=` | export the last shortlist |
