# Tool Catalog

The contract between the LLM and the backend. Tools are OpenAI-style function definitions (`{"type":"function","function":{name, description, parameters}}`), registered in `app/agent/registry.py` with a JSON schema and a handler. Descriptions must be specific, because the model picks tools from them.

Return values are compact JSON. Lists return at most `limit` items (default 10, max 50) plus `total`. All data comes from the tables in DATA_MODEL.md.

---

## Candidate tools

### `search_candidates`
Search the pool by structured criteria and/or free text.
- **parameters:** `query?: string` (matches `summary`, `last_job_title`, `primary_major`, `Experience.job_title`), `skills?: string[]` (any or all, see `skills_mode`), `skills_mode?: enum[any, all]`, `min_years?: number`, `max_years?: number`, `degree?: string`, `major?: string`, `location?: string`, `certification?: string`, `limit?: int`
- **returns:** `{ total, candidates: [{ candidate_id, full_name, last_job_title, last_company, total_experience, highest_degree, location, skills[] }] }`

### `get_candidate_profile`
Full profile for one candidate: the Candidate row, skills, experience, education and certifications.
- **parameters:** `candidate_id: int`, `sections?: enum[skills, experience, education, certifications][]`

### `list_skills`
The distinct skill vocabulary from `Skill`, with how many candidates have each one. Used to map user wording to real skill names.
- **parameters:** `query?: string`, `limit?: int`

## JD / document tools

### `list_documents`
JDs and reference documents in `data/docs/`.
- **parameters:** `doc_type?: enum[jd, policy, interview_guide, other]`, `query?: string`
- **returns:** `{ total, docs: [{ doc_id, title, doc_type }] }`

### `get_document`
- **parameters:** `doc_id: string`, `max_chars?: int`

### `extract_job_spec`
Turns a JD (`doc_id`, or raw text the user pasted) into a structured JobSpec (see DATA_MODEL.md), saved in `AgentMemory` as `active_job_spec` for this chat. The extraction is LLM-assisted. Skill names are then mapped onto the real `Skill` vocabulary, and unmapped skills are reported.
- **parameters:** `doc_id?: string`, `jd_text?: string`, `title?: string`
- **returns:** `{ job_spec, unmapped_skills[] }`

## Matching

### `match_candidates`
**The "find the best candidate" tool.** Scores the pool, or a given set of candidates, against a JobSpec using `services/scoring.py`.
- **parameters:** `job_spec?: object` (default: the chat's `active_job_spec`), `candidate_ids?: int[]`, `weights?: {skills, experience, relevance, education, certifications}`, `must_have_skills?: string[]`, `limit?: int`
- **returns:** `{ total_scored, results: [{ candidate_id, full_name, score (0-100), breakdown{}, matched_skills[], missing_skills[], flags[] }] }`. The shortlist is saved as `last_shortlist` in AgentMemory.

### `compare_candidates`
Side-by-side comparison of 2 to 6 candidates against the active JobSpec.
- **parameters:** `candidate_ids: int[]`, `job_spec?: object`

## Analytics

### `get_pool_stats`
Aggregates over the candidate pool, used for charts.
- **parameters:** `metric: enum[skill_supply, experience_distribution, degree_mix, major_mix, location_mix, certification_mix]`, `skills?: string[]`, `candidate_ids?: int[]`
- **returns:** `{ metric, series: [{ label, value }] }`

## Presentation

### `render_view`
Shows a rich view in the chat. Call it after the data tools. The server hydrates the content from the DB or the saved shortlist.
- **parameters:** `template: enum` (see RESPONSE_TEMPLATES.md), `title: string`, `candidate_ids?: int[]`, `doc_id?: string`, `metric?: string`, `options?: { highlight?: string[], sort_by?: string, chart_type?: enum[bar, radar, doughnut, line] }`
- **returns to the LLM:** `{ rendered: true, block_id }`
- **side effect:** an SSE `ui_block` event

---

## Fallback when the gateway lacks native function calling

The same catalog is described in the system prompt. The model replies with exactly one JSON object, either `{"tool": name, "arguments": {...}}` or `{"final": "..."}`. The loop parses that object, validates it against the same schema, and continues. Both modes share one registry.

## Adding a tool (checklist)

1. Write the handler in `app/tools/<family>.py` as a pure function: repository + validated args in, dict out. SQL goes only in `repository.py`.
2. Register the schema and handler in `registry.py`, keeping a deterministic order.
3. Document the tool here.
4. Add a test in `tests/tools/`.
