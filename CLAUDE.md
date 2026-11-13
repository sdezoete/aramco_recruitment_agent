# Recruitment Agent

A chat-based recruiting assistant. A recruiter types in plain language ("find the best 5 candidates for this reservoir engineer JD"). The LLM uses **function calling** to query the candidate database, JDs and other documents, then shows the results as rich UI views (ranked tables, candidate cards, comparison matrices, charts) inside a normal chat stream.

@docs/AIRGAP_DEPLOYMENT_STANDARD.md

The standard imported above is binding: we develop here, release to `usb_x_y_z`, and deploy to an air-gapped Windows server. Wheels only, no CDNs, and the `PRODUCTION` switch in `.env`.

Project docs. Read the relevant one before a non-trivial change:
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): **the server tables (`T_IIR_ARIF_*`) and the app's memory table, authoritative.** Source: `docs/schema/db_structure_server.txt`. Fields marked TO CONFIRM carry a stated assumption; don't build more on them until the user answers
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md): the candidate profile shape the repository returns, the scoring model and the hard filters
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, request flow, agent loop, SSE protocol
- [docs/TOOLS.md](docs/TOOLS.md): tool catalog, the contract between the LLM and the backend
- [docs/HARMONY.md](docs/HARMONY.md): **harmony format rules** (roles, channels, history policy, gateway fallbacks). Read this before touching `app/llm/` or `app/agent/`
- [docs/RESPONSE_TEMPLATES.md](docs/RESPONSE_TEMPLATES.md): UI block types the frontend renders
- [docs/DECISIONS.md](docs/DECISIONS.md): decision log. Append an entry when you make an architectural choice
- [docs/ROADMAP.md](docs/ROADMAP.md): phases, status, open questions
- [DEPLOY.md](DEPLOY.md) and [DEPLOY-NOTES.md](DEPLOY-NOTES.md): server install and per-release server settings

## Project-specific values

| | |
|---|---|
| App package / version | `app/`, `__version__` in `app/__init__.py` |
| Release folder | `usb_x_y_z\recruitment-agent\` + `DEPLOY-NOTES.md` |
| Python | 3.11 x64 (`.venv/`) |
| Dev DB | SQL Server 2022 Developer, `localhost` default instance, database `recruitment`, Windows auth, ODBC Driver 17 for SQL Server |
| Prod DB | SQL Server; set through `DB_*` in the server `.env` (server/auth TBD, see ROADMAP) |
| LLM | OpenAI-compatible chat-completions in the **harmony** format. Prod: DeepSeek 4.1 Flash through the corporate MaaS gateway (API key). Dev: OpenAI (`gpt-5.4-mini`), or the mock LLM in `tests/mock_llm.py` |

## Stack

- **Backend:** FastAPI + Uvicorn (HTTPS via `--ssl-certfile/--ssl-keyfile` when `PRODUCTION=True`), `pyodbc` for SQL Server (parameterized SQL, no ORM), `httpx` for the LLM client, `truststore` so Python trusts the Windows certificate store (internal CA).
- **Frontend:** vanilla HTML/CSS/JS, no build step. Chart.js is **vendored** in `static/vendor/` (no CDN).

## Commands (repo root, PowerShell)

```
.venv\Scripts\python -m pip install -r requirements-dev.txt       # dev install (online)
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000  # dev server, PRODUCTION=False -> http://127.0.0.1:8000
.venv\Scripts\python -m app                                        # how the server runs it (HTTPS if TLS_* set)
.venv\Scripts\python -m tests.mock_llm --port 8001                 # mock LLM (--raw-harmony, --no-tools)
#   then run the app with RA_LLM_BASE_URL=http://127.0.0.1:8001/v1 RA_LLM_MODEL=mock-harmony
.venv\Scripts\python -m pytest                                     # tests (e2e tests use the local DB + mock LLM; also runs tests/js via node)
node --test "tests/js/*.test.mjs"                                 # frontend unit tests only (dev-only, fake DOM)
# http://127.0.0.1:8000/dev/gallery   every UI template from real data (dev only)
# http://127.0.0.1:8000/?q=<prompt>   deep link that sends a prompt on load
powershell -ExecutionPolicy Bypass -File scripts\1-build-wheels.ps1   # build + verify wheels\
powershell -ExecutionPolicy Bypass -File scripts\make-usb.ps1         # build usb_x_y_z\
sqlcmd -S localhost -E -d recruitment -Q "..."                     # inspect dev DB (run sqlcmd from PowerShell, not Git Bash)
sqlcmd -S localhost -E -d recruitment -i sql\01_dev_server_tables.sql; .venv\Scripts\python scripts\seed_dev_db.py   # reset dev data
```

## Target layout

```
app/
  __init__.py            __version__
  __main__.py            `python -m app`: uvicorn + TLS checks (self-signed/expired refused in prod)
  main.py                FastAPI: static, /api/meta, /api/health, /api/chat (SSE), export, dev gallery
  config.py              .env loader + PRODUCTION switch + validation (RA_<KEY> overrides)
  llm/harmony.py         harmony roles/channels, stream parser for leaked tokens
  llm/client.py          OpenAI-compatible client (stream, tools, probe, 400-adaptation)
  agent/loop.py          agent loop (LLM <-> tools) -> SSE events; prompted-JSON fallback
  agent/prompts.py       identity + developer instructions
  agent/registry.py      tool schemas, validation (jsonschema), dispatch
  tools/handlers.py      tool implementations; tools/render.py hydrates UI blocks; tools/context.py state
  services/              scoring.py, jobspec.py (JD -> spec), documents.py, normalize.py
  db/connection.py       pyodbc connection from DB_* settings
  db/repository.py       ALL SQL lives here
static/  index.html, css/app.css, js/{app,renderers,panel,profile-nav,charts,markdown,sse,dom}.js, vendor/, dev/ (gallery)
data/docs/               JDs and reference documents (fake samples in git)
sql/                     01_dev_server_tables.sql (dev only), 02_agent_memory.sql (dev + server, run by a DBA),
                         03_recommended_indexes.sql (optional request to the table owner)
data/reference/          application_statuses.csv (status code -> stage, order, open for matching; placeholder)
docs/schema/             db_structure_server.txt (the server table structure as supplied)
scripts/  1-build-wheels.ps1, 2-install-offline.ps1, make-usb.ps1, run-server.bat, seed_dev_db.py (dev only)
tests/   unit tests, e2e agent tests, API tests, mock_llm.py, js/ (frontend tests on node --test)
```

## Core rules

1. **The server tables are fixed.** Use only the `T_IIR_ARIF_*` tables and columns in `docs/DATA_DICTIONARY.md`; never alter them. The dev DB holds an exact copy (`sql/01_dev_server_tables.sql` + fake data from `scripts/seed_dev_db.py`). The app writes only to its own `T_IIR_ARIF_AGENT_MEMORY` (`sql/02_agent_memory.sql`). The user allows app-owned tables, but each one needs a `sql/` script, a DECISIONS entry and a DEPLOY-NOTES line. If a feature needs data that isn't in the server tables, stop and ask.
   The app's `candidate_id` is `ARIF_ID` (`CANDIDATE_ID` is the unique ATS id). Use the **original** columns only; the `NORM_*` columns are not used (ADR-012). `NATIONAL_ID`, `GENDER` and `COUNTRY` (nationality) are never selected. `SAUDI_EXPAT` is only the requisition's hire-type filter (ADR-010). Names and text can be Arabic, so keep everything Unicode-safe.
   The server holds 350k–500k candidates: pre-filter and cap in SQL, use set-based `IN (subquery)` rather than `OR` across tables, and re-time with a scaled-up dev DB after changing a query (ADR-014). Status codes map through `data/reference/application_statuses.csv` (ADR-013).
2. **All SQL lives in `db/repository.py`**, parameterized (`?` placeholders). Never build SQL from strings that contain user or LLM input.
3. **The LLM never invents the data shown in the UI.** Data tools return IDs and facts. `render_view` takes IDs plus a template, and the server hydrates the values from the DB.
4. **Scoring is deterministic Python** (`services/scoring.py`) with a per-criterion breakdown. The LLM explains results and may adjust weights through tool arguments.
5. **No protected attributes in ranking.** The current schema has none; keep it that way in queries and prompts. Any compliance-driven criterion needs a DECISIONS entry first.
6. **Candidate data is PII.** Commit no real data. Do not log profiles. Send the LLM only the fields a tool needs.
7. **Tool contract changes are API changes.** Update `docs/TOOLS.md`, the registry, and the tests together. New UI block type: update `docs/RESPONSE_TEMPLATES.md` and add a renderer.
8. **Frontend renderers** are pure `render(block) -> HTMLElement` functions that use `textContent` and never `innerHTML` with data.

## LLM conventions (OpenAI-compatible + harmony, see docs/HARMONY.md)

- `POST {LLM_BASE_URL}/chat/completions` with `tools=[{"type":"function","function":{...}}]`, `tool_choice="auto"` and `stream=true`. The system message carries the harmony identity, date and `Reasoning:` level. The developer message carries the instructions.
- **Analysis (reasoning) is never shown to users and never sent back to the model.** Completed turns keep only the user text and the final answer.
- Parse `tool_calls[].function.arguments` with `json.loads` and validate against the schema before executing. On failure, return `{"error": ...}` as the tool result so the model can retry.
- Cap the loop at `AGENT_MAX_STEPS` (default 8). Handle `finish_reason` values `tool_calls`, `stop` and `length`.
- Never assume a gateway feature. The client adapts on a 400 response, and without native tools the loop switches to prompted-JSON tool calls. Any change to this must keep the three e2e modes (native, raw harmony, no tools) passing.
- In production the UI shows `LLM_DISPLAY_NAME` (ARIF). In dev it shows the model id.

## Working style

- Keep the agent loop thin. Logic lives in `tools/` and `services/` and is testable without an LLM. Tests use a mock LLM server and the local `recruitment` DB, read-only, or fixtures.
- The project path contains a space (`Python Projects`), so always quote paths.
- `docs_other_project/` holds reference docs from a sibling project that follows the same deployment standard. Read it for patterns; it is not part of this app and is never shipped.
