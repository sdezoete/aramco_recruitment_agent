# Aramco Recruitment Agent (Step 1 to Step 4)

This repository now includes:
- Step 1: deterministic SQL data access layer + schema contracts + CrewAI tools
- Step 2: persisted session memory for multi-turn clarification state
- Step 3: agent role modules + task contracts
- Step 4: orchestrated pause/resume recruitment flow
- Step 5: stronger deterministic requirements parser + impact-driven clarification policy
- LLM parser mode: OpenAI-backed requirement extraction with local-AI switch

## Structure
- `app/config.py`: environment-driven settings
- `app/db/`: SQL connection and repositories
- `app/schemas/`: Pydantic contracts
- `app/tools/`: CrewAI tool wrappers
- `app/services/`: state/memory orchestration helpers
- `app/agents/`: deterministic role implementations
- `app/tasks/`: task wrappers over agents
- `app/orchestration/recruitment_flow.py`: end-to-end flow with clarification pause/resume
- `app/services/requirements_parser.py`: rule-first JD parser (LLM-pluggable later)
- `app/services/llm.py`: OpenAI client wrapper for requirements extraction
- `app/services/clarification_policy.py`: question generation and answer application policy
- `resumes/`: sample resumes (Data Scientist, AI Engineer, Generative AI Specialist)
- `sql/001_create_agent_session_memory.sql`: Step 2 memory table DDL

## LLM configuration
- `.env` supports both cloud and local AI routing:
- `USE_LOCAL_AI=false` uses OpenAI via `OPENAI_API_KEY` and `OPENAI_MODEL`
- `USE_LOCAL_AI=true` reserves local model routing for airgapped production setup

## Quick start
1. Create `.env` using `.env.example`.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Apply SQL DDL in `sql/001_create_agent_session_memory.sql` if using SQL backend.
4. Run smoke checks:
   - `python run_smoke_test.py`
   - `python run_memory_smoke_test.py`
   - `python run_flow_demo.py`
    - `python run_api_smoke_test.py`

## API endpoints (development)
- Start API server: `python run_api.py`
- Health: `GET /health`
- ATS mock:
   - `GET /ats/requisitions`
   - `GET /ats/requisitions/{requisition_id}/applications?limit=20`
   - `GET /ats/candidates/{candidate_id}`
- Recruitment flow:
   - `POST /requisition/ingest`
   - `POST /requisition/{id}/clarify`
   - `POST /search`
   - `GET /candidate/{id}`
   - `POST /feedback`

## Demo note
- `run_flow_demo.py` forces `SESSION_MEMORY_BACKEND=file` so it can run without SQL memory table setup.

## Airgapped packaging
On an internet-connected machine:
- `pip download -r requirements.txt -d wheels`

On the airgapped machine:
- `pip install --no-index --find-links wheels -r requirements.txt`
