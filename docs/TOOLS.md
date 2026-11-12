# Tool Catalog

The contract between the LLM and the backend. Tools are OpenAI-style function definitions (`{"type":"function","function":{name, description, parameters}}`), registered in `app/agent/registry.py` with a JSON schema and a handler. Descriptions must be specific, because the model picks tools from them.

Return values are compact JSON. Lists return at most `limit` items (default 10, max 50) plus `total`. All data comes from the `T_IIR_ARIF_*` tables (DATA_DICTIONARY.md). **`candidate_id` everywhere is `ARIF_ID`.** Hire type (Saudi/Expat), location (`CANDIDATE_FLAG`) and application status are **filters only**; they are never scored.

---

## Candidate tools

### `search_candidates`
Search the pool by structured criteria and/or free text.
- **parameters:** `query?: string` (English or Arabic; matches `SUMMARY`, `CURRENT_JOB_TITLE`, `TEXT_TOKENS`, experience `TITLE`/`NORM_TITLE`), `skills?: string[]` (mapped onto `NORM_SKILL`; any or all, see `skills_mode`), `skills_mode?: enum[any, all]`, `min_years?: number`, `max_years?: number`, `degree?: string` (minimum level), `major?: string`, `min_gpa?: number (1-4)`, `hire_type?: enum[Saudi, Expat, any]`, `location?: string[]` (`CANDIDATE_FLAG`), `application_status?: string[]`, `exclude_statuses?: string[]`, `limit?: int`
- **returns:** `{ total, candidates: [{ candidate_id, full_name, last_job_title, last_company, total_experience, highest_degree, location, hire_type, application_status, skills[] }] }`

### `get_candidate_profile`
Full profile for one candidate: identity and status fields, summary, skills, experience, education and assessments (inductive / numerical / verbal, 0–100). Never includes `NATIONAL_ID` or `GENDER`.
- **parameters:** `candidate_id?: int` (ARIF id) **or** `ats_id?: int` (the recruiting system's unique CANDIDATE_ID), `sections?: enum[skills, experience, education, assessments][]`. Includes `gpa` (1–4 scale), `pipeline_stage` and `status_included`.

### `list_skills`
The skill vocabulary: distinct `ORG_SKILL` spellings grouped by canonical form (e.g. "MS Excel" = "Excel"), with approximate candidate counts and the number of spellings. Used to map user wording to real skill names.
- **parameters:** `query?: string`, `limit?: int`

## JD / document tools

### `list_documents`
JDs and reference documents in `data/docs/`.
- **parameters:** `doc_type?: enum[jd, policy, interview_guide, other]`, `query?: string`
- **returns:** `{ total, docs: [{ doc_id, title, doc_type }] }`

### `get_document`
- **parameters:** `doc_id: string`, `max_chars?: int`

### `set_job_spec`
Sets the chat's active JobSpec (see DATA_MODEL.md), saved in `T_IIR_ARIF_AGENT_MEMORY` as `active_job_spec`.
- With `doc_id` (a JD file) or `jd_text` (a pasted JD), a deterministic extractor (`services/jobspec.py`) drafts the spec. It reads only the Requirements and Preferred sections: skills from the grouped `ORG_SKILL` vocabulary, minimum years, degree and majors. It also detects the hire type from phrases such as "Hire type: Saudi", "Saudi nationals only" or "expatriate contract".
- Explicit fields override the draft. That is how the LLM corrects the draft or sets requirements described in the chat.
- Skill names are mapped onto the vocabulary. Unmapped skills are reported, because they can't be scored.
- **parameters:** `doc_id?`, `jd_text?`, `title?`, `required_skills?: string[]`, `preferred_skills?: string[]`, `min_years?`, `degree?` (e.g. Bachelor, Master, PhD), `min_gpa?` (1–4, flag only), `majors?`, `title_keywords?`, `hire_type?: enum[Saudi, Expat, any]`, `locations?: string[]`, `weights?`
- **returns:** the spec (with `degree` as a name), `source`, and `unmapped_skills[]` when there are any

## Matching

### `match_candidates`
**The "find the best candidate" tool.** Scores the pool, or a given set of candidates, against a JobSpec using `services/scoring.py`.
- Requires an active spec: call `set_job_spec` first.
- **parameters:** `candidate_ids?: int[]`, `weights?: {skills, experience, relevance, education, assessments}`, `must_have_skills?: string[]`, `exclude_statuses?: string[]` (extra exclusions), `include_all_statuses?: bool` (turn off the default exclusions from `application_statuses.csv`), `limit?: int`
- With no `candidate_ids`, the pool is the candidates that have any spec skill **and pass the spec's hard filters** (hire type, locations, status codes not open for matching, extra excluded statuses), capped at `MATCH_MAX_POOL`. Small pools (fewer than 50) score every eligible candidate, so near-misses still show.
- **returns:** `{ filters, total_scored, results: [{ candidate_id, full_name, score (0-100), breakdown{}, matched_skills[], missing_skills[], flags[] }] }`. Flags include `missing_must_have:<skill>`, `below_min_years`, `no_assessment`, `hire_type_mismatch`, `location_mismatch`, `status_not_open` and `below_min_gpa`. The shortlist is saved as `last_shortlist` in `T_IIR_ARIF_AGENT_MEMORY`.

### `compare_candidates`
Side-by-side comparison of 2 to 6 candidates against the active JobSpec.
- **parameters:** `candidate_ids: int[]` (uses the active spec)

## Analytics

### `get_pool_stats`
Aggregates over the candidate pool, used for charts.
Also the way to discover valid filter values (`location_mix`, `status_mix`, `hire_type_mix`).
- **parameters:** `metric: enum[skill_supply, experience_distribution, degree_mix, major_mix, location_mix, status_mix, stage_mix, source_mix, hire_type_mix]` (`status_mix` and `stage_mix` are ordered by the pipeline order in the status file), `candidate_ids?: int[]`
- **returns:** `{ metric, series: [{ label, value }] }`

## Presentation

### `render_view`
Shows a rich view in the chat. Call it after the data tools. The server hydrates the content from the DB or the saved shortlist.
- **parameters:** `template: enum` (see RESPONSE_TEMPLATES.md), `title: string`, `candidate_ids?: int[]`, `doc_ids?: string[]`, `metric?: string` (pool metrics or `shortlist_scores`), `options?: { limit?: int, chart_type?: enum[bar, doughnut, line, radar], scope?: enum[pool, shortlist] }`
- **returns to the LLM:** `{ rendered: true, block_id }`
- **side effect:** an SSE `ui_block` event

---

## Fallback when the gateway lacks native function calling

The same catalog is described in the system prompt. The model replies with exactly one JSON object, either `{"tool": name, "arguments": {...}}` or `{"final": "..."}`. The loop parses that object, validates it against the same schema, and continues. Both modes share one registry.

## Adding a tool (checklist)

1. Write the handler in `app/tools/<family>.py` as a pure function: repository + validated args in, dict out. SQL goes only in `repository.py`.
2. Register the schema and handler in `registry.py`, keeping a deterministic order.
3. Document the tool here.
4. Add a test in `tests/`.
