# Roadmap

## Status (2026-11-11)
The first working version is built: backend, harmony-aware LLM client, tools, scoring, the full frontend, and the dev gallery. 19 tests pass, including e2e agent turns against the local DB in all three gateway modes. OpenAI is configured as the dev LLM, but the machine's `OPENAI_API_KEY` is rejected (`invalid_api_key`), so a valid key must go in `.env`. Version `0.1.0` (not released).

## Phase 0: Pipeline
- [x] AIRGAP_DEPLOYMENT_STANDARD, DEPLOY.md, DEPLOY-NOTES.md
- [x] `scripts/1-build-wheels.ps1`, `2-install-offline.ps1`, `make-usb.ps1`
- [x] Git repo: github.com/sdezoete/aramco_recruitment_agent (`main`). History restarted 2026-11-11; the old implementation is kept only as a local bundle backup
- [x] Pin exact versions in `requirements.txt`, then build and verify `wheels/` (27 wheels, offline install + pip check clean, 2026-11-11)
- [x] `make-usb.ps1` dry run (fallback mode): correct file set, no `.env`
- [x] Vendor Chart.js 4.4.7 into `static/vendor/`

## Phase 1: Foundations
- [x] `app/config.py` (`.env` + PRODUCTION rules), `db/connection.py`, `db/repository.py` against the fixed schema
- [x] `services/scoring.py` + tests
- [x] `llm/client.py` + harmony + mock LLM + capability probe
- [x] `/api/health`

## Phase 2: Agent + tools
- [x] Tool handlers + registry + tests
- [x] Agent loop (native tools, leaked-harmony parsing, prompted-JSON fallback), `/api/chat` SSE

## Phase 3: Frontend
- [x] Chat shell, SSE client, thinking indicator, preambles, tool chips, theme toggle, mobile layout
- [x] All 9 renderers + chart/table toggle + dev gallery
- [x] Follow-up action chips, CSV export, `?q=` deep link
- [ ] Verify with a real OpenAI key (blocked: the machine key is invalid)
- [ ] JD file upload (.docx/.pdf) from the UI. For now JDs come from `data/docs/` or are pasted into the chat

## Phase 4: Production hardening
- [x] HTTPS settings + certificate checks in `python -m app`, `run-server.bat`, audit log (metadata only)
- [ ] Startup task script (Scheduled Task as SYSTEM) + firewall rule
- [ ] Verify against the MaaS gateway: tools / stream / developer role (see HARMONY.md, "Checking on the server")
- [ ] First release `usb_0_1_0`

## Open questions
1. **Authoritative table structure:** the user is supplying it. DATA_MODEL.md currently mirrors the local `recruitment` DB. Is that DB the final structure?
2. **Prod DB connection:** server name or instance, Windows vs SQL authentication, and a read-only login (plus write access on `AgentMemory` only)? Is ODBC Driver 17 or 18 installed on the server?
3. ~~Dev LLM endpoint~~: OpenAI (decided 2026-11-11). It needs a valid key in `.env`.
4. **Gateway capabilities:** does the MaaS model support `tools` (function calling) and `stream`? The design falls back if not, but native support is much better. What is the exact model id of DeepSeek 4.1 Flash on the gateway?
5. **JD source:** files in `data/docs/` only, or also another system?
6. **Server specifics:** install path, port, certificate location (the sibling project uses `D:\ssl_certificate\`), and the users / SSO in front of the app.
