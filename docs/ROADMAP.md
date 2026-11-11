# Roadmap

## Status (2026-11-11)
Documentation, the deployment standard, and the release scripts exist. No application code yet. Version `0.1.0` (not released).

## Phase 0: Pipeline
- [x] AIRGAP_DEPLOYMENT_STANDARD, DEPLOY.md, DEPLOY-NOTES.md
- [x] `scripts/1-build-wheels.ps1`, `2-install-offline.ps1`, `make-usb.ps1`
- [ ] `git init`, first commit (make-usb uses git-tracked files)
- [x] Pin exact versions in `requirements.txt`, then build and verify `wheels/` (27 wheels, offline install + pip check clean, 2026-11-11)
- [x] `make-usb.ps1` dry run (fallback mode): correct file set, no `.env`
- [ ] Vendor Chart.js into `static/vendor/`

## Phase 1: Foundations
- [ ] `app/config.py` (`.env` + PRODUCTION rules), `db/connection.py`, `db/repository.py` against the fixed schema
- [ ] `services/scoring.py` + tests
- [ ] `llm/client.py` + mock LLM server for tests + capability probe
- [ ] `/api/health`

## Phase 2: Agent + tools
- [ ] Tool handlers + registry + tests
- [ ] Agent loop (native tools + prompted-JSON fallback), `/api/chat` SSE

## Phase 3: Frontend
- [ ] Chat shell, SSE client, tool chips, theme toggle
- [ ] Renderers: ranked_table, candidate_cards, candidate_profile, comparison_matrix, score_radar, chart, jd_card, document_hits, kpi_strip

## Phase 4: Production hardening
- [ ] HTTPS (org certificate), `run-server.bat`, startup task, audit log
- [ ] First release `usb_0_1_0`

## Open questions
1. **Authoritative table structure:** the user is supplying it. DATA_MODEL.md currently mirrors the local `recruitment` DB. Is that DB the final structure?
2. **Prod DB connection:** server name or instance, Windows vs SQL authentication, and a read-only login (plus write access on `AgentMemory` only)? Is ODBC Driver 17 or 18 installed on the server?
3. **Dev LLM endpoint:** which compatible endpoint to use on this machine (the sibling project uses OpenAI)?
4. **Gateway capabilities:** does the MaaS model support `tools` (function calling) and `stream`? The design falls back if not, but native support is much better.
5. **JD source:** files in `data/docs/` only, or also another system?
6. **Server specifics:** install path, port, certificate location (the sibling project uses `D:\ssl_certificate\`), and the users / SSO in front of the app.
