# Aramco Recruitment Agent (Step 1 to Step 4)

This repository now includes:
- Step 1: deterministic SQL data access layer + schema contracts + CrewAI tools
- Step 2: persisted session memory for multi-turn clarification state
- Step 3: agent role modules + task contracts
- Step 4: orchestrated pause/resume recruitment flow

## Structure
- `app/config.py`: environment-driven settings
- `app/db/`: SQL connection and repositories
- `app/schemas/`: Pydantic contracts
- `app/tools/`: CrewAI tool wrappers
- `app/services/`: state/memory orchestration helpers
- `app/agents/`: deterministic role implementations
- `app/tasks/`: task wrappers over agents
- `app/orchestration/recruitment_flow.py`: end-to-end flow with clarification pause/resume
- `sql/001_create_agent_session_memory.sql`: Step 2 memory table DDL

## Quick start
1. Create `.env` using `.env.example`.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Apply SQL DDL in `sql/001_create_agent_session_memory.sql` if using SQL backend.
4. Run smoke checks:
   - `python run_smoke_test.py`
   - `python run_memory_smoke_test.py`
   - `python run_flow_demo.py`

## Demo note
- `run_flow_demo.py` forces `SESSION_MEMORY_BACKEND=file` so it can run without SQL memory table setup.

## Airgapped packaging
On an internet-connected machine:
- `pip download -r requirements.txt -d wheels`

On the airgapped machine:
- `pip install --no-index --find-links wheels -r requirements.txt`
