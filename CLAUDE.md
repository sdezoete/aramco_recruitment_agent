# Recruitment Agent

A chat-based recruiting assistant. A recruiter types in plain language ("find the best 5 candidates for this reservoir engineer JD"). The LLM uses **function calling** to query the candidate database, JDs and other documents, then shows the results as rich UI views (ranked tables, candidate cards, comparison matrices, charts) inside a normal chat stream.

@docs/AIRGAP_DEPLOYMENT_STANDARD.md

The standard imported above is binding: we develop here, release to `usb_x_y_z`, and deploy to an air-gapped Windows server. Wheels only, no CDNs, and the `PRODUCTION` switch in `.env`.

Project docs. Read the relevant one before a non-trivial change:
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md): **the DB schema (fixed, supplied by the user)** and the scoring model
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, request flow, agent loop, SSE protocol
- [docs/TOOLS.md](docs/TOOLS.md): tool catalog, the contract between the LLM and the backend
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
| LLM | OpenAI-compatible chat-completions; prod = corporate MaaS gateway; dev = any compatible endpoint set in `.env` |

## Stack

- **Backend:** FastAPI + Uvicorn (HTTPS via `--ssl-certfile/--ssl-keyfile` when `PRODUCTION=True`), `pyodbc` for SQL Server (parameterized SQL, no ORM), `httpx` for the LLM client, `truststore` so Python trusts the Windows certificate store (internal CA).
- **Frontend:** vanilla HTML/CSS/JS, no build step. Chart.js is **vendored** in `static/vendor/` (no CDN).

## Commands (repo root, PowerShell)

```
.venv\Scripts\python -m pip install -r requirements.txt           # dev install (online)
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000  # dev server, PRODUCTION=False
.venv\Scripts\python -m pytest                                     # tests
powershell -ExecutionPolicy Bypass -File scripts\1-build-wheels.ps1   # build + verify wheels\
powershell -ExecutionPolicy Bypass -File scripts\make-usb.ps1         # build usb_x_y_z\
sqlcmd -S localhost -E -d recruitment -Q "..."                     # inspect dev DB
```

## Target layout

```
app/
  __init__.py          __version__
  main.py              FastAPI app, routes, static mount, startup checks
  config.py            .env loader + PRODUCTION switch + validation
  llm/client.py        OpenAI-compatible client (stream, tools, capability probe, fallbacks)
  agent/loop.py        agent loop (LLM <-> tools), emits SSE events
  agent/prompts.py     system prompt
  agent/registry.py    tool schemas + handlers
  tools/               candidates.py, documents.py, analytics.py, render.py
  services/scoring.py  deterministic, explainable candidate-to-JD scoring
  db/connection.py     pyodbc connection from DB_* settings
  db/repository.py     ALL SQL lives here
static/  index.html, css/, js/, js/renderers/, vendor/
data/docs/             JDs and reference documents (samples only in git)
scripts/  1-build-wheels.ps1, 2-install-offline.ps1, make-usb.ps1, run-server.bat
tests/
```

## Core rules

1. **The DB schema is fixed.** Use only the tables and columns in `docs/DATA_MODEL.md`. Never create, alter, or drop tables, and never add columns. If a feature needs data that is not in the schema, stop and ask. The app writes only to `AgentMemory`; every other table is read-only.
2. **All SQL lives in `db/repository.py`**, parameterized (`?` placeholders). Never build SQL from strings that contain user or LLM input.
3. **The LLM never invents the data shown in the UI.** Data tools return IDs and facts. `render_view` takes IDs plus a template, and the server hydrates the values from the DB.
4. **Scoring is deterministic Python** (`services/scoring.py`) with a per-criterion breakdown. The LLM explains results and may adjust weights through tool arguments.
5. **No protected attributes in ranking.** The current schema has none; keep it that way in queries and prompts. Any compliance-driven criterion needs a DECISIONS entry first.
6. **Candidate data is PII.** Commit no real data. Do not log profiles. Send the LLM only the fields a tool needs.
7. **Tool contract changes are API changes.** Update `docs/TOOLS.md`, the registry, and the tests together. New UI block type: update `docs/RESPONSE_TEMPLATES.md` and add a renderer.
8. **Frontend renderers** are pure `render(block) -> HTMLElement` functions that use `textContent` and never `innerHTML` with data.

## LLM conventions (OpenAI-compatible)

- `POST {LLM_BASE_URL}/chat/completions` with `tools=[{"type":"function","function":{...}}]` and `tool_choice="auto"`, `stream=true`.
- Parse `tool_calls[].function.arguments` with `json.loads`, then validate against the tool's schema before executing. On invalid JSON or schema failure, return an error tool message so the model can retry.
- Return each result as `{"role":"tool","tool_call_id":..., "content": json}`. Support several tool calls in one turn.
- Cap the loop at `AGENT_MAX_STEPS` (default 8). Handle `finish_reason` values `tool_calls`, `stop` and `length`.
- **Capability fallback:** if the gateway rejects `tools`, `stream` or `response_format`, retry without it. Without native tools, use prompted JSON tool calls (documented in ARCHITECTURE.md).
- The model name shown to users comes from `LLM_DISPLAY_NAME`.

## Working style

- Keep the agent loop thin. Logic lives in `tools/` and `services/` and is testable without an LLM. Tests use a mock LLM server and the local `recruitment` DB, read-only, or fixtures.
- The project path contains a space (`Python Projects`), so always quote paths.
- `docs_other_project/` holds reference docs from a sibling project that follows the same deployment standard. Read it for patterns; it is not part of this app and is never shipped.
