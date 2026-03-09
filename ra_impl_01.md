Got it. Below is a **CrewAI-first implementation plan** that fits your constraints:

* **Airgapped production** (no internet, no LinkedIn, no external scraping)
* **ATS integration via internal APIs** (JR number → job description)
* **SQL database with 4 tables**: `CANDIDATE`, `EXPERIENCE`, `EDUCATION`, `SKILLS`
* `CANDIDATE` includes `summary`, `resume_text_dump`, and optional `verbal/math/insight` test scores
* **Windows + VSCode + Python 3.11.7**
* We do this **step-by-step**: first plan, then we generate deployable code for each step.

---

## Target outcome (what the system must do)

1. Recruiter enters **Job Requisition Number** (or pastes JD text).
2. System fetches JD from ATS API (if JR number).
3. System extracts structured requirements.
4. System asks a small set of clarifying questions (only if needed).
5. System searches candidates in SQL (structured fields + optional text search).
6. System ranks and explains candidates with evidence.
7. System proposes “archetype differences” (DL Expert vs DS vs MLOps, etc.) and tradeoffs.

---

# Step-by-step implementation plan (CrewAI)

## Step 0 — Repo skeleton + offline packaging strategy

**Goal:** Ensure everything runs offline on the airgapped server.

### Deliverables

* Python project structure for CrewAI app (clean separation of concerns)
* `requirements.txt` + **wheelhouse** strategy
* Configuration via `.env` (but no secrets committed)

### Offline approach

* On a connected machine:

  * `pip download -r requirements.txt -d wheels/`
* Move `wheels/` + repo to airgapped server
* Install via:

  * `pip install --no-index --find-links wheels -r requirements.txt`

> We’ll keep dependencies minimal and stable. No runtime calls to the internet.

---

## Step 1 — Data access layer (SQL tools) + schema contract

**Goal:** A deterministic tool layer that exposes candidate data safely to agents.

### Tools (CrewAI Tools)

1. **CandidateQueryTool**

   * Executes parameterized SQL queries
   * Returns rows as `list[dict]`
2. **CandidateProfileTool**

   * Given `candidate_id`, returns:

     * Candidate core fields (from `CANDIDATE`)
     * Joined experience, education, skills
3. **ATSJobRequisitionTool**

   * `get_job_description(req_number)` via internal API
   * Returns JD text + metadata

### Data structures

Define strict Pydantic models (so agents don’t hallucinate fields):

* `JobRequisitionRaw`:

  * `req_id`, `title`, `department`, `location`, `jd_text`, `metadata`
* `JobRequirements`:

  * must-haves / nice-to-haves / experience / education / keywords / constraints
* `CandidateRecord` (flattened) + optionally nested:

  * `candidate`, `experience[]`, `education[]`, `skills[]`
* `SearchPlan`:

  * SQL filters, joins, optional text query, ranking weights
* `CandidateScore`:

  * scoring breakdown + evidence pointers

### Notes for your DB

Because you have 4 tables, we’ll implement a **canonical join strategy**:

* `CANDIDATE(candidate_id PK)`
* `EXPERIENCE(candidate_id FK)`
* `EDUCATION(candidate_id FK)`
* `SKILLS(candidate_id FK)`

And treat:

* `CANDIDATE.resume_text_dump` and `CANDIDATE.summary` as optional “semantic/keyword support”
* `test_score_verbal`, `test_score_math`, `test_score_insight` as optional ranking features

---

## Step 2 — Memory model (conversation + requisition state)

**Goal:** Keep the system consistent across multi-turn clarification and refinement.

### Memory layers (recommended)

1. **Session Memory (per chat_id / requisition_id)**

   * Persist:

     * raw JD
     * extracted requirements
     * clarifying Q/A
     * last query plan
     * last result set ids
   * Implementation options (airgapped-friendly):

     * SQL table `AGENT_SESSION_MEMORY`
     * OR local JSON files per session (for MVP)
2. **Short-term in-run memory**

   * Within one execution, pass objects between tasks.

### Suggested DB table for memory

`AGENT_SESSION_MEMORY`

* `session_id`
* `requisition_id`
* `state_json` (the whole state as JSON)
* `created_at`, `updated_at`

This keeps everything auditable.

---

## Step 3 — Agents (CrewAI roles)

**Goal:** Clear separation of responsibilities; tools enforce grounding.

### Agent 1: **Intake Agent**

* Input: requisition number or JD text
* Uses: `ATSJobRequisitionTool`
* Output: `JobRequisitionRaw`

### Agent 2: **Requirements Analyst Agent**

* Input: JD text
* Output: `JobRequirements` (strict JSON / Pydantic)
* Also outputs:

  * `confidence`
  * `missing_fields` list

### Agent 3: **Clarification Agent**

* Input: `JobRequirements` + `missing_fields` + (optional) current candidate count estimate
* Output:

  * 3–7 questions max, each mapped to a schema field
* After answers, updates `JobRequirements`

### Agent 4: **Search Planner Agent**

* Input: finalized `JobRequirements`
* Output: `SearchPlan`
* Must only use known schema fields (validated)

### Agent 5: **Retrieval Agent**

* Uses: `CandidateQueryTool` / `CandidateProfileTool`
* Executes `SearchPlan` deterministically
* Output: candidate pool + structured candidate records

### Agent 6: **Ranker & Explainer Agent**

* Input: candidates + `JobRequirements`
* Output:

  * ranked list
  * per-candidate score breakdown
  * evidence (which fields matched, which experience lines, which skills)

### Agent 7: **Archetype Comparator Agent**

* Input: top N candidates + requirements
* Output:

  * clusters/archetypes (DL Specialist vs DS vs MLOps)
  * tradeoffs
  * “If you mean X, prefer archetype A; if you mean Y, prefer archetype B”

> In v1, clustering can be simple rules-based (skills/title patterns). We can add embeddings later if needed (still offline).

---

## Step 4 — Tasks (CrewAI Tasks) and outputs

**Goal:** Each task produces a typed artifact saved in memory and returned to API/UI.

### Task list (in order)

1. **Fetch JD**

   * Output: `JobRequisitionRaw`
2. **Parse Requirements**

   * Output: `JobRequirements` + confidence
3. **Generate Clarification Questions (conditional)**

   * Output: `ClarificationQuestions[]`
4. **Apply Clarification Answers (conditional)**

   * Output: updated `JobRequirements`
5. **Create Search Plan**

   * Output: `SearchPlan`
6. **Run Candidate Retrieval**

   * Output: `CandidatePool` (ids + records)
7. **Rank + Explain**

   * Output: `RankedCandidates[]`
8. **Archetype Comparison**

   * Output: `ArchetypeReport`

Each task writes to `AGENT_SESSION_MEMORY.state_json`.

---

## Step 5 — Flow / orchestration design

**Goal:** A deterministic orchestrator around CrewAI so the system is robust.

### Orchestration approach

* You run a **single “RecruitmentCrew”** with conditional branching:

  * If input is requisition number → call ATS tool
  * If requirements confidence low or missing fields → ask clarification
  * Then search → rank → archetypes
* The orchestrator (your Flask/FastAPI route or CLI) manages:

  * session_id
  * step state
  * whether to pause for user answers

### State machine

* `INGESTED → PARSED → (NEEDS_CLARIFICATION?) → READY_TO_SEARCH → SEARCHED → PRESENTED → REFINED`

This is important because clarification is multi-turn.

---

## Step 6 — Search strategy (SQL-first, optional text)

**Goal:** Make it fast, explainable, and airgap-friendly.

### Retrieval (recommended 2-stage)

1. **SQL filters first** (hard constraints):

   * location, degree level, years exp, required skills presence
2. **Ranking next** (soft constraints):

   * skill coverage
   * title fit
   * domain keywords from experience/employers
   * test scores (if present)
   * keyword match in `summary` / `resume_text_dump`

### Text search options (offline)

* MVP: SQL `LIKE` / Full-Text Search if enabled in SQL Server
* Later: embeddings (still offline), but only if needed

---

## Step 7 — Auditing and “no hallucinations” guardrails

**Goal:** Trustworthy results for recruiters and compliance.

### Guardrails

* Agents cannot invent DB fields: schema validator rejects unknown fields.
* Retrieval results must cite:

  * table + column + row id (candidate_id)
  * or snippet from stored text dump
* Store:

  * search plan
  * executed SQL + parameters
  * top candidate set + scoring breakdown

---

# What we will do next (Step 1 code)

Per your instruction “first plan, then code per step”:

### Next step to generate code for deployment:

**Step 1: Data access layer + tools + Pydantic schemas**

* `db/connection.py` (pyodbc)
* `db/repository.py` (safe query methods)
* `tools/ats_tool.py`
* `tools/candidate_query_tool.py`
* `tools/candidate_profile_tool.py`
* `schemas/*.py` (Pydantic models)
* Example query templates for the 4 tables

If you confirm nothing else, I’ll assume:

* SQL Server via `pyodbc`
* Windows auth (Trusted Connection) unless you tell me it’s SQL auth
* ATS API is reachable from the airgapped network (internal URL)

Say “go step 1” and I’ll output the full code bundle for Step 1 (ready to paste into VSCode).
