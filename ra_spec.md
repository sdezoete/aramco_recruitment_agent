Below is a build-spec outline (agentic AI recruitment) written so a code agent can turn it into an implementation plan. It assumes: (1) job requisitions can be pasted or uploaded, (2) candidate data lives in SQL plus resume full text + summary, (3) the system must not “invent” requirements—only interpret what’s provided and ask clarifying questions when needed.

---

## 1) Goals and non-goals

### Goals

* Ingest a job requisition (JR) and extract structured requirements.
* Ask targeted clarification questions only when needed to disambiguate or reduce a candidate set.
* Translate the final requirements into **traceable** SQL + optional semantic search over resume text.
* Return ranked candidates with explanations grounded in data (fields + resume evidence).
* Suggest **role-fit alternatives** (e.g., “Deep Learning Specialist” vs “Generalist Data Scientist”) and explain tradeoffs.

### Non-goals (v1)

* Auto-reject decisions without human review.
* Writing employment offers / compensation benchmarking (unless explicitly added later).
* Scraping external sources (LinkedIn etc.) unless later approved.

---

## 2) Key user journeys

### Journey A — Recruiter inputs a JR

1. Recruiter provides JR text or uploads document.
2. System extracts:

   * Must-have skills / nice-to-have skills
   * Minimum years experience
   * Education requirements (degree level, majors)
   * Industry/domain preferences
   * Location/work mode
   * Seniority + job family
3. System checks “confidence” and asks 3–7 clarifying questions max (only the highest impact).
4. Recruiter answers.
5. System searches and returns:

   * Top candidates (ranked)
   * Evidence per candidate (skills, titles, employers, scores)
   * Gaps + risks
   * Alternative archetypes and why

### Journey B — Recruiter refines search

* Recruiter adjusts constraints (“drop PhD”, “must have MLOps”, “prefer Arabic”, etc.)
* System re-runs search and shows deltas (why some candidates entered/left top list)

### Journey C — Hiring manager review

* Hiring manager opens a candidate pack:

  * structured fit summary
  * evidence + resume snippets
  * interview questions tailored to gaps

---

## 3) System architecture (components)

### 3.1 API layer

* `POST /requisition/ingest` (text/file metadata) → returns `requisition_id`
* `POST /requisition/{id}/clarify` (answers) → returns updated structured requirements
* `POST /search` (requisition_id + overrides) → returns ranked candidates + evidence
* `GET /candidate/{id}` → candidate details + evidence
* `POST /feedback` (thumbs up/down, “why not”, short notes)

### 3.2 Core services (microservice-friendly)

1. **Requisition Parser Service**

   * Inputs: JR text
   * Outputs: structured requirement JSON + confidence + missing fields list
2. **Clarification Orchestrator**

   * Generates minimal question set (impact-driven)
   * Maintains state across turns (chat_id / requisition_id)
3. **Query Planner**

   * Converts requirement JSON → SQL filters + weights + optional semantic query
   * Outputs: query plan object (auditable)
4. **Candidate Retrieval**

   * Executes SQL
   * (Optional) executes semantic search over resume text/summaries (vector DB or SQL full-text)
5. **Ranker + Explainer**

   * Scores candidates, generates “why this person” grounded in fields/snippets
6. **Archetype Comparator**

   * Detects competing candidate clusters (“DL Expert”, “DS Generalist”, “MLOps Engineer”)
   * Produces tradeoff explanation + recommended archetype based on clarifications
7. **Audit + Observability**

   * Logs every prompt, query, decision, and evidence snippet ids

---

## 4) Data model assumptions (SQL)

You said you have structured fields plus resume full text and summary. The system should treat these as:

### 4.1 Canonical candidate record (example)

* `candidate_id`
* `education_level`, `degree_major`, `university`, `gpa`
* `job_titles[]` (or normalized table)
* `employers[]`
* `skills[]` (normalized skill table + proficiency if available)
* `years_experience_total`
* `years_experience_relevant` (derived)
* `assessments`: `test_score_x`, `test_score_y` (optional)
* `resume_text` (full text)
* `resume_summary`
* `location`, `work_authorization`, `languages`

### 4.2 Supporting tables (recommended)

* `candidate_experience` (title, employer, start/end, description)
* `candidate_skill` (skill, level, last_used)
* `skill_taxonomy` (aliases, parent/child mapping)
* `job_requisition` (raw text + structured JSON + answers)
* `search_runs` (requisition_id, filters, timestamps, result_ids)

---

## 5) Agentic workflow (state machine)

### States

1. **INGESTED**
2. **PARSED**
3. **NEEDS_CLARIFICATION** (if critical missing)
4. **READY_TO_SEARCH**
5. **SEARCH_EXECUTED**
6. **RESULTS_PRESENTED**
7. **REFINED** (iterative loop)

### Transition logic (high-level)

* If parser confidence < threshold OR must-have list too broad → NEEDS_CLARIFICATION
* Else → READY_TO_SEARCH
* After results → if too many matches (e.g., >300) or too few (<5) → propose refinements

---

## 6) Clarification question design (impact-driven)

The clarifier should ask questions that materially change ranking/filtering. Examples:

### High-impact (ask early)

* “Is MLOps (deployment/monitoring) a must-have, or just desirable?”
* “What’s the minimum years experience in production ML?”
* “Do you need deep learning specialization (CV/NLP) or general ML engineering?”
* “Any hard constraints: location, onsite, clearance, nationality, language?”
* “Which matters more: research depth (papers) vs shipping systems (APIs, pipelines)?”

### Low-impact (ask later or not at all)

* “Preferred IDE” / tooling preferences unless explicitly in JR.

### Question policy

* Max 7 questions per cycle.
* Each question must map to a field/constraint in the requirement schema.
* Each question must state the tradeoff: “This decides between DL Specialists vs Generalist DS profiles.”

---

## 7) Requirement schema (output of parser + clarifications)

Define a strict JSON schema (example fields):

* `role_title`
* `seniority` (junior/mid/senior/lead)
* `must_have_skills`: [{skill, min_years?, weight}]
* `nice_to_have_skills`
* `domain_keywords` (e.g., “oil & gas”, “finance”)
* `education`: {min_level, preferred_majors, min_gpa?}
* `experience`: {min_years_total, min_years_relevant, required_titles?}
* `work_constraints`: {location, onsite_policy, travel, language, authorization}
* `scoring_preferences`: {weight_skills, weight_title_fit, weight_domain, weight_scores, weight_education}
* `exclusions`: {skills_to_avoid?, industries_to_avoid?, etc.}
* `confidence` + `missing_fields`

This schema is the contract between “LLM reasoning” and “deterministic retrieval”.

---

## 8) Query planning and retrieval strategy

### 8.1 Two-stage retrieval (recommended)

1. **Broad SQL filter** to get a candidate pool:

   * location/authorization
   * min years
   * required education level (if hard)
   * required must-have skills presence (not proficiency yet)
2. **Ranking stage**:

   * weighted skill match
   * title similarity
   * employer/industry relevance
   * test scores (if applicable)
   * semantic similarity on resume summary/text (optional)

### 8.2 SQL generation rules (guardrails)

* LLM does **not** execute SQL directly.
* LLM outputs a **Query Plan JSON** with:

  * `filters` (field/operator/value)
  * `joins` (allowed list)
  * `ranking_features`
  * `limit`
* A deterministic “SQL Builder” converts plan → parameterized SQL.
* Every filter must reference a known schema field (validated).

### 8.3 Skill normalization

* Use `skill_taxonomy` to map synonyms:

  * “PyTorch” ↔ “pytorch”
  * “Deep Learning” ↔ “Neural Networks”
  * “ML Ops” ↔ “MLOps” ↔ “Model Monitoring”
* Store normalized skill ids for reliable SQL joins.

---

## 9) Ranking and explanation (grounded, auditable)

### Scoring (example)

* Skill match score (coverage + recency + min years)
* Title fit score (title embeddings or taxonomy mapping)
* Domain score (keywords + employer industry)
* Education score (level, major, GPA)
* Assessment score (if available)
* Semantic relevance (resume summary/text)

### Explanation output per candidate

* “Matched must-haves: PyTorch (3y), Kubernetes (2y), Model deployment”
* “Evidence: resume snippet ids or experience row references”
* “Gaps: no monitoring stack (Prometheus/MLflow) found”
* “Risk notes: short tenure pattern / missing production projects” (only if data supports it)

---

## 10) Archetype comparison (your “DL Experts vs DS” example)

### Cluster detection

From the pool, build clusters using:

* dominant skill groups (DL / classical ML / data engineering / MLOps)
* recent job titles
* project keywords in resume summaries

### Archetype objects

* `archetype_name`: “Deep Learning Specialist”
* `typical_strengths`: e.g., “CV/NLP, model architecture, research”
* `typical_risks`: e.g., “less pipeline ownership”
* `best_for`: e.g., “model innovation”
* `top_candidates`: list

### Tie-back to clarification

Show: “If you prioritize shipping models into production, Archetype B wins; if you prioritize novel model performance, Archetype A wins.”

---

## 11) Safety, privacy, and compliance

* PII redaction in prompts (mask phone/email/national IDs).
* Role-based access control: recruiter vs hiring manager vs admin.
* Full audit trail:

  * input JR
  * extracted requirements JSON
  * clarification Q/A
  * query plan + final SQL
  * candidates returned
* Model prompt injection defenses:

  * never let JR text override system policies
  * treat JR as data, not instructions

---

## 12) Deliverables for the code agent (what to build)

### 12.1 Core deliverables (MVP)

1. Requirement schema + validator
2. Requisition parsing prompt + parser implementation
3. Clarification orchestrator (state + Q generation)
4. Query planner producing query-plan JSON
5. SQL builder + execution + result normalization
6. Ranker + explainer
7. Basic UI/endpoint contracts for iterative refinement
8. Logging/audit tables

### 12.2 Nice-to-have (Phase 2)

* Vector search on resume text (Chroma/pgvector/etc.)
* Skill taxonomy management UI
* Feedback-driven re-ranking (learning-to-rank later)

---

## 13) Acceptance criteria (testable)

* Given a JR, the system outputs a valid requirement JSON (passes schema validation).
* Clarification questions are ≤7 and each maps to a missing/uncertain field.
* Generated query plan references only approved fields/joins.
* SQL is parameterized and executes within performance budget.
* Each top candidate has ≥3 grounded evidence points.
* Archetype summary is generated when multiple clusters exist, with explicit tradeoffs.

---

## 14) Example end-to-end artifacts (what the code agent should output)

For one JR, the system should produce these artifacts (stored + retrievable):

1. `job_requisition.raw_text`
2. `job_requisition.requirements_json_v1`
3. `job_requisition.clarification_questions`
4. `job_requisition.clarification_answers`
5. `job_requisition.requirements_json_final`
6. `search_run.query_plan_json`
7. `search_run.executed_sql` (or SQL template + params)
8. `search_run.results` (candidate ids + scores + evidence ids)
9. `archetype_report`

---

If you want, I can also provide:

* A concrete JSON Schema (draft-07 style) for `requirements_json` and `query_plan_json`
* A folder structure + file-level spec (e.g., `services/requisition_parser`, `services/query_planner`, `db/sql_builder.py`, etc.)
* A sample prompt pack for the LLM parts (parser, clarifier, archetype comparator) with strict tool/field constraints
