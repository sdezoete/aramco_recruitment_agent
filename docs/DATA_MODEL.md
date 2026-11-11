# Data Model

**The schema is supplied by the user and is fixed.** Never create, alter, or drop tables or columns. If a feature needs data that isn't here, ask the user. Update this file only when the user supplies a schema change.

- Engine: Microsoft SQL Server. Dev uses SQL Server 2022 Developer at `localhost` (default instance), database `recruitment`, Windows authentication, ODBC Driver 17 for SQL Server.
- Access: `pyodbc` with parameterized SQL in `app/db/repository.py` only.
- Schema snapshot below was read from the dev DB on 2026-11-11. **Pending:** the user is supplying the authoritative table structure. Reconcile this file against it when it arrives.

## Tables (schema `dbo`)

### Candidate
| column | type | null | notes |
|---|---|---|---|
| candidate_id | int | NO | **PK** |
| full_name | nvarchar(255) | YES | |
| location | nvarchar(100) | YES | |
| total_experience | float | YES | years |
| highest_degree | nvarchar(100) | YES | free text (e.g. "BSc", "Master") |
| primary_major | nvarchar(100) | YES | |
| last_job_title | nvarchar(100) | YES | |
| last_company | nvarchar(100) | YES | |
| summary | nvarchar(max) | YES | free text |

### Skill
| column | type | null | notes |
|---|---|---|---|
| skill_id | int | NO | **PK** |
| skill_name | nvarchar(100) | YES | **UNIQUE** |

### CandidateSkill
| column | type | null | notes |
|---|---|---|---|
| candidate_id | int | NO | **PK**, FK → Candidate.candidate_id |
| skill_id | int | NO | **PK**, FK → Skill.skill_id |

Has no proficiency level or years: a skill is either present or absent.

### Experience
| column | type | null | notes |
|---|---|---|---|
| experience_id | int | NO | **PK** |
| candidate_id | int | YES | FK → Candidate |
| job_title | nvarchar(255) | YES | |
| company | nvarchar(255) | YES | |
| location | nvarchar(100) | YES | |
| years_experience | float | YES | years in this role |

### Education
| column | type | null | notes |
|---|---|---|---|
| education_id | int | NO | **PK** |
| candidate_id | int | YES | FK → Candidate |
| institute | nvarchar(255) | YES | |
| major | nvarchar(100) | YES | |
| degree | nvarchar(100) | YES | |
| gpa | nvarchar(10) | YES | text; parse defensively (e.g. "3.6/4", "4.2/5") |

### Certification
| column | type | null | notes |
|---|---|---|---|
| certification_id | int | NO | **PK** |
| candidate_id | int | YES | FK → Candidate |
| name | nvarchar(255) | YES | |

### AgentMemory (the only table the app writes to)
| column | type | null | notes |
|---|---|---|---|
| chat_id | nvarchar(50) | NO | **PK** (with key) |
| key | nvarchar(100) | NO | **PK**. `key` is a reserved word in T-SQL, so always quote it as `[key]` |
| value | nvarchar(max) | NO | JSON text |
| updated_at | datetime | YES | |

Used for conversation state and preferences per chat (for example the active JD or the last shortlist). Upsert with `MERGE` or `UPDATE … IF @@ROWCOUNT = 0 INSERT`.

Dev row counts on 2026-11-11: Candidate 10, Skill 10, CandidateSkill 26, Experience 10, Education 10, Certification 10, AgentMemory 17.

## Not in the DB

- **Jobs and JDs** have no table. JDs come from documents in `data/docs/` or from text the user pastes or uploads (see TOOLS.md). Requirements are extracted from a JD into a structured *JobSpec* in memory, which can be stored in `AgentMemory` for the chat.
- Applications and pipeline stages have no table either, so pipeline analytics are limited to the candidate pool (skill supply, experience and degree distribution).

## Scoring model (`services/scoring.py`)

Inputs are a **JobSpec** and candidate rows. A JobSpec is: `required_skills[]`, `preferred_skills[]`, `min_years`, `degrees[]`, `majors[]`, `certifications[]`, `title_keywords[]` and `weights`.

| criterion | default weight | computation (each scored 0–1) |
|---|---:|---|
| skills | 0.40 | matched required skills / required count (via CandidateSkill→Skill.skill_name, normalized), plus a bonus of up to 0.1 for preferred skills, capped at 1 |
| experience | 0.25 | `min(total_experience / min_years, 1.0)`; 1.0 when `min_years` is 0 |
| relevance | 0.15 | overlap of title keywords with `last_job_title` and `Experience.job_title`, weighted by `years_experience` |
| education | 0.10 | degree level meets or exceeds the requirement, plus major matches `primary_major` / `Education.major` |
| certifications | 0.10 | coverage of the required certifications (fuzzy name match on `Certification.name`) |

- Skill and certification names are normalized for matching: case-folded, punctuation stripped, with a small alias map in code (for example "ms excel" → "excel").
- A missing required skill adds a `missing_must_have` flag. The candidate is not excluded by default.
- Weights can be overridden by the tool argument and are normalized to sum to 1.
- Output always includes the breakdown, `matched_skills` and `missing_skills`.
