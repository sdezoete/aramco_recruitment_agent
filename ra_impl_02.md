Perfect — here is **Step 1 (deployable code bundle)**: DB access layer + Pydantic schemas + CrewAI tools (DB tools + ATS placeholder tool). It’s written for **Windows + Python 3.11.7 + SQL Server via pyodbc** and uses your table names:

* `arif_recruitment`
* `T_IIR_ARIF_CANDIDATE`
* `T_IIR_ARIF_EDUCATION`
* `T_IIR_ARIF_EXPERIENCE`
* `T_IIR_ARIF_SKILLS`

This step does **not** implement the full Crew yet — it only provides the deterministic tool layer and contracts the agents will rely on.

---

## Project structure (Step 1)

```
recruitment_agent/
  app/
    __init__.py
    config.py
    db/
      __init__.py
      connection.py
      repository.py
      sql_builder.py
    schemas/
      __init__.py
      requisition.py
      candidate.py
      search.py
    tools/
      __init__.py
      ats_job_tool.py
      candidate_query_tool.py
      candidate_profile_tool.py
  run_smoke_test.py
  requirements.txt
```

---

## requirements.txt (minimal, airgap-friendly)

```txt
pyodbc==5.2.0
pydantic==2.7.4
pydantic-settings==2.3.4
requests==2.32.3
crewai==0.86.0
```

> If your CrewAI version differs internally, pin it to your approved version and re-download wheels on a connected machine.

---

## app/config.py

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQL Server
    DB_DRIVER: str = "{ODBC Driver 17 for SQL Server}"
    DB_SERVER: str = "cw-002918"
    DB_NAME: str = "arif_recruitment"
    DB_TRUSTED_CONNECTION: str = "yes"
    DB_USERNAME: str | None = None
    DB_PASSWORD: str | None = None

    # ATS (placeholder, you said you already have real code)
    ATS_BASE_URL: str = "https://internal-ats.example.local"
    ATS_TOKEN: str | None = None
    ATS_TIMEOUT_SECONDS: int = 20


settings = Settings()
```

---

## app/db/connection.py

```python
import pyodbc
from app.config import settings


def open_db_connection() -> pyodbc.Connection:
    """
    Creates a new DB connection.
    For safety and predictability, we create connections per operation
    (or per request) instead of sharing a global connection.
    """
    conn_kwargs = {
        "driver": settings.DB_DRIVER,
        "server": settings.DB_SERVER,
        "database": settings.DB_NAME,
        "autocommit": True,
    }

    # Trusted connection (Windows auth)
    if settings.DB_TRUSTED_CONNECTION.lower() in ("yes", "true", "1"):
        conn_kwargs["trusted_connection"] = "yes"
        return pyodbc.connect(**conn_kwargs)

    # SQL auth (if needed later)
    if not settings.DB_USERNAME or not settings.DB_PASSWORD:
        raise ValueError("DB_USERNAME/DB_PASSWORD required when not using trusted connection")

    conn_str = (
        f"DRIVER={settings.DB_DRIVER};"
        f"SERVER={settings.DB_SERVER};"
        f"DATABASE={settings.DB_NAME};"
        f"UID={settings.DB_USERNAME};"
        f"PWD={settings.DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True)
```

---

## app/db/sql_builder.py (safe helper: parameterized IN clauses)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class SQLQuery:
    sql: str
    params: list[Any]


def build_in_clause_params(values: Sequence[Any]) -> tuple[str, list[Any]]:
    """
    Returns: ("?, ?, ?", [v1, v2, v3]) for parameterized IN (...) usage.
    """
    values = list(values)
    if not values:
        # Caller should handle empty set separately, but this prevents invalid SQL.
        return "(NULL)", []
    placeholders = ", ".join(["?"] * len(values))
    return f"({placeholders})", values
```

---

## app/schemas/requisition.py (ATS/JD structures)

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class JobRequisitionRaw(BaseModel):
    req_id: str = Field(..., description="Job requisition number")
    title: str | None = None
    department: str | None = None
    location: str | None = None
    jd_text: str = Field(..., description="Raw job description text")
    metadata: dict = Field(default_factory=dict)
```

---

## app/schemas/candidate.py (DB output contracts)

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateCore(BaseModel):
    candidate_id: str = Field(..., description="Primary identifier")
    full_name: str | None = None
    email: str | None = None

    summary: str | None = None
    resume_text_dump: str | None = None

    # Optional test scores (some candidates)
    test_score_verbal: float | None = None
    test_score_math: float | None = None
    test_score_insight: float | None = None

    # Optional useful fields (if present in your table)
    current_title: str | None = None
    current_employer: str | None = None
    location: str | None = None


class EducationRow(BaseModel):
    candidate_id: str
    degree_level: str | None = None
    major: str | None = None
    institution: str | None = None
    gpa: float | None = None
    start_date: str | None = None
    end_date: str | None = None


class ExperienceRow(BaseModel):
    candidate_id: str
    job_title: str | None = None
    employer: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class SkillRow(BaseModel):
    candidate_id: str
    skill: str
    proficiency: str | None = None
    years: float | None = None
    last_used: str | None = None


class CandidateProfile(BaseModel):
    candidate: CandidateCore
    education: list[EducationRow] = Field(default_factory=list)
    experience: list[ExperienceRow] = Field(default_factory=list)
    skills: list[SkillRow] = Field(default_factory=list)
```

---

## app/schemas/search.py (query-plan structures for later steps)

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateSearchFilters(BaseModel):
    # Structured filters (all optional)
    candidate_ids: list[str] | None = None

    # Skills filter: match any or all
    skills_any: list[str] | None = None
    skills_all: list[str] | None = None

    # Keywords for text dump/summary search
    text_keywords_any: list[str] | None = None

    # Education filters
    min_gpa: float | None = None
    degree_levels_any: list[str] | None = None
    majors_any: list[str] | None = None

    # Test score filters
    min_test_verbal: float | None = None
    min_test_math: float | None = None
    min_test_insight: float | None = None

    # Basic paging
    limit: int = 50
    offset: int = 0


class CandidateSearchResult(BaseModel):
    candidate_id: str
    score_hint: float | None = Field(
        default=None,
        description="Optional pre-score hint; in step 1 we may not compute a score."
    )
    reasons: list[str] = Field(default_factory=list)


class CandidateSearchResponse(BaseModel):
    total_estimated: int | None = None
    results: list[CandidateSearchResult]
```

---

## app/db/repository.py (DB access + joins)

This file intentionally does **not** assume exact column names beyond a small set.
You should update the `COLUMN_MAP_*` dictionaries to match your true columns.

```python
from __future__ import annotations

from typing import Any, Iterable

import pyodbc

from app.db.connection import open_db_connection
from app.db.sql_builder import build_in_clause_params
from app.schemas.candidate import (
    CandidateCore, CandidateProfile, EducationRow, ExperienceRow, SkillRow
)
from app.schemas.search import CandidateSearchFilters, CandidateSearchResponse, CandidateSearchResult


# ----------------------------
# Tables (given by you)
# ----------------------------
T_CANDIDATE = "T_IIR_ARIF_CANDIDATE"
T_EDU = "T_IIR_ARIF_EDUCATION"
T_EXP = "T_IIR_ARIF_EXPERIENCE"
T_SKL = "T_IIR_ARIF_SKILLS"


# ----------------------------
# Column maps (UPDATE THESE)
# ----------------------------
# These maps define which DB columns to select and how they map into schema fields.
# Adjust the right-hand side to your real DB column names.
COLUMN_MAP_CANDIDATE = {
    "candidate_id": "candidate_id",
    "full_name": "full_name",
    "email": "email",
    "summary": "summary",
    "resume_text_dump": "resume_text_dump",
    "test_score_verbal": "test_score_verbal",
    "test_score_math": "test_score_math",
    "test_score_insight": "test_score_insight",
    "current_title": "current_title",
    "current_employer": "current_employer",
    "location": "location",
}

COLUMN_MAP_EDU = {
    "candidate_id": "candidate_id",
    "degree_level": "degree_level",
    "major": "major",
    "institution": "institution",
    "gpa": "gpa",
    "start_date": "start_date",
    "end_date": "end_date",
}

COLUMN_MAP_EXP = {
    "candidate_id": "candidate_id",
    "job_title": "job_title",
    "employer": "employer",
    "start_date": "start_date",
    "end_date": "end_date",
    "description": "description",
}

COLUMN_MAP_SKL = {
    "candidate_id": "candidate_id",
    "skill": "skill",
    "proficiency": "proficiency",
    "years": "years",
    "last_used": "last_used",
}


def _select_list(column_map: dict[str, str]) -> str:
    """
    SELECT list like: candidate_id AS candidate_id, full_name AS full_name, ...
    """
    return ", ".join([f"{db_col} AS {alias}" for alias, db_col in column_map.items()])


def _fetchall_dict(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


class RecruitmentRepository:
    """
    Deterministic DB access methods.
    Agents should NOT write SQL themselves; they call these methods via tools.
    """

    # ---------- Candidate core ----------
    def get_candidate_core_by_ids(self, candidate_ids: list[str]) -> list[CandidateCore]:
        if not candidate_ids:
            return []

        in_clause, params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_CANDIDATE)}
        FROM {T_CANDIDATE}
        WHERE candidate_id IN {in_clause}
        """
        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            data = _fetchall_dict(cur)
        return [CandidateCore(**row) for row in data]

    # ---------- Education ----------
    def get_education_by_candidate_ids(self, candidate_ids: list[str]) -> list[EducationRow]:
        if not candidate_ids:
            return []
        in_clause, params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_EDU)}
        FROM {T_EDU}
        WHERE candidate_id IN {in_clause}
        """
        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            data = _fetchall_dict(cur)
        return [EducationRow(**row) for row in data]

    # ---------- Experience ----------
    def get_experience_by_candidate_ids(self, candidate_ids: list[str]) -> list[ExperienceRow]:
        if not candidate_ids:
            return []
        in_clause, params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_EXP)}
        FROM {T_EXP}
        WHERE candidate_id IN {in_clause}
        """
        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            data = _fetchall_dict(cur)
        return [ExperienceRow(**row) for row in data]

    # ---------- Skills ----------
    def get_skills_by_candidate_ids(self, candidate_ids: list[str]) -> list[SkillRow]:
        if not candidate_ids:
            return []
        in_clause, params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_SKL)}
        FROM {T_SKL}
        WHERE candidate_id IN {in_clause}
        """
        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            data = _fetchall_dict(cur)
        return [SkillRow(**row) for row in data]

    # ---------- Candidate profile (joined in app layer) ----------
    def get_candidate_profiles(self, candidate_ids: list[str]) -> list[CandidateProfile]:
        cores = self.get_candidate_core_by_ids(candidate_ids)
        if not cores:
            return []

        edu = self.get_education_by_candidate_ids(candidate_ids)
        exp = self.get_experience_by_candidate_ids(candidate_ids)
        skl = self.get_skills_by_candidate_ids(candidate_ids)

        edu_by = {}
        for r in edu:
            edu_by.setdefault(r.candidate_id, []).append(r)

        exp_by = {}
        for r in exp:
            exp_by.setdefault(r.candidate_id, []).append(r)

        skl_by = {}
        for r in skl:
            skl_by.setdefault(r.candidate_id, []).append(r)

        profiles: list[CandidateProfile] = []
        for c in cores:
            profiles.append(
                CandidateProfile(
                    candidate=c,
                    education=edu_by.get(c.candidate_id, []),
                    experience=exp_by.get(c.candidate_id, []),
                    skills=skl_by.get(c.candidate_id, []),
                )
            )
        return profiles

    # ---------- Search (MVP) ----------
    def search_candidates(self, filters: CandidateSearchFilters) -> CandidateSearchResponse:
        """
        MVP search: structured filters + optional keyword matching on candidate summary/text.
        This is intentionally conservative and explainable. Ranking comes in Step 3+.
        """

        where_clauses: list[str] = ["1=1"]
        params: list[Any] = []

        # Candidate ID filter
        if filters.candidate_ids:
            in_clause, in_params = build_in_clause_params(filters.candidate_ids)
            where_clauses.append(f"c.candidate_id IN {in_clause}")
            params.extend(in_params)

        # Test scores (if columns exist)
        if filters.min_test_verbal is not None:
            where_clauses.append("c.test_score_verbal >= ?")
            params.append(filters.min_test_verbal)
        if filters.min_test_math is not None:
            where_clauses.append("c.test_score_math >= ?")
            params.append(filters.min_test_math)
        if filters.min_test_insight is not None:
            where_clauses.append("c.test_score_insight >= ?")
            params.append(filters.min_test_insight)

        # Text keyword search (basic LIKE on summary + text dump)
        if filters.text_keywords_any:
            likes = []
            for kw in filters.text_keywords_any:
                likes.append("(c.summary LIKE ? OR c.resume_text_dump LIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%"])
            where_clauses.append("(" + " OR ".join(likes) + ")")

        # Skills (ANY / ALL) using EXISTS subqueries on skills table
        if filters.skills_any:
            in_clause, in_params = build_in_clause_params([s.lower() for s in filters.skills_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_SKL} s
                        WHERE s.candidate_id = c.candidate_id
                          AND LOWER(s.skill) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        if filters.skills_all:
            # Require each skill exists (AND of EXISTS)
            for skill in filters.skills_all:
                where_clauses.append(
                    f"""EXISTS (
                            SELECT 1 FROM {T_SKL} s2
                            WHERE s2.candidate_id = c.candidate_id
                              AND LOWER(s2.skill) = ?
                        )"""
                )
                params.append(skill.lower())

        # Education filters (degree level / major / GPA) using EXISTS on education table
        if filters.min_gpa is not None:
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e
                        WHERE e.candidate_id = c.candidate_id
                          AND e.gpa >= ?
                    )"""
            )
            params.append(filters.min_gpa)

        if filters.degree_levels_any:
            in_clause, in_params = build_in_clause_params([d.lower() for d in filters.degree_levels_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e2
                        WHERE e2.candidate_id = c.candidate_id
                          AND LOWER(e2.degree_level) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        if filters.majors_any:
            in_clause, in_params = build_in_clause_params([m.lower() for m in filters.majors_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e3
                        WHERE e3.candidate_id = c.candidate_id
                          AND LOWER(e3.major) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        # Paging
        limit = max(1, min(filters.limit, 200))
        offset = max(0, filters.offset)

        sql = f"""
        SELECT c.candidate_id
        FROM {T_CANDIDATE} c
        WHERE {" AND ".join(where_clauses)}
        ORDER BY c.candidate_id
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        params.extend([offset, limit])

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        results = [CandidateSearchResult(candidate_id=str(r[0])) for r in rows]
        return CandidateSearchResponse(results=results)
```

---

## app/tools/candidate_query_tool.py (CrewAI Tool: search)

```python
from __future__ import annotations

import json
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.db.repository import RecruitmentRepository
from app.schemas.search import CandidateSearchFilters


class CandidateQueryToolInput(BaseModel):
    filters_json: str = Field(
        ...,
        description="JSON string matching CandidateSearchFilters (MVP search)."
    )


class CandidateQueryTool(BaseTool):
    name: str = "candidate_query_tool"
    description: str = (
        "Search candidate IDs in SQL using safe, parameterized filters. "
        "Returns candidate_id list. Use this before fetching full profiles."
    )
    args_schema = CandidateQueryToolInput

    def _run(self, filters_json: str) -> str:
        repo = RecruitmentRepository()
        filters = CandidateSearchFilters(**json.loads(filters_json))
        resp = repo.search_candidates(filters)
        # Return a compact JSON list for easy LLM consumption
        return json.dumps(
            {
                "count": len(resp.results),
                "candidate_ids": [r.candidate_id for r in resp.results],
            },
            ensure_ascii=False
        )
```

---

## app/tools/candidate_profile_tool.py (CrewAI Tool: profiles)

```python
from __future__ import annotations

import json
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.db.repository import RecruitmentRepository


class CandidateProfileToolInput(BaseModel):
    candidate_ids: list[str] = Field(..., description="List of candidate IDs (max ~50 recommended).")


class CandidateProfileTool(BaseTool):
    name: str = "candidate_profile_tool"
    description: str = (
        "Fetch full candidate profiles (candidate core + education + experience + skills) "
        "from SQL for a list of candidate IDs."
    )
    args_schema = CandidateProfileToolInput

    def _run(self, candidate_ids: list[str]) -> str:
        repo = RecruitmentRepository()
        # Basic safety limit to avoid huge payloads
        candidate_ids = candidate_ids[:50]
        profiles = repo.get_candidate_profiles(candidate_ids)
        return json.dumps(
            {
                "count": len(profiles),
                "profiles": [p.model_dump() for p in profiles],
            },
            ensure_ascii=False
        )
```

---

## app/tools/ats_job_tool.py (ATS placeholder tool)

You said you already have ATS code — so here are placeholders + required fields.

```python
from __future__ import annotations

import json
import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.config import settings
from app.schemas.requisition import JobRequisitionRaw


class ATSJobToolInput(BaseModel):
    requisition_number: str = Field(..., description="ATS job requisition number, e.g., JR-12345")


class ATSJobRequisitionTool(BaseTool):
    name: str = "ats_job_requisition_tool"
    description: str = (
        "Fetch job requisition details from ATS using an internal API. "
        "Returns: req_id, title, department, location, jd_text, metadata. "
        "This is a placeholder - replace request logic with your existing ATS integration."
    )
    args_schema = ATSJobToolInput

    def _run(self, requisition_number: str) -> str:
        # ---- PLACEHOLDER IMPLEMENTATION ----
        # Replace this with your existing ATS client code.
        #
        # Required output fields for downstream steps:
        # - req_id (string)
        # - jd_text (string)
        # Optional:
        # - title, department, location, metadata dict

        url = f"{settings.ATS_BASE_URL}/api/requisitions/{requisition_number}"
        headers = {}
        if settings.ATS_TOKEN:
            headers["Authorization"] = f"Bearer {settings.ATS_TOKEN}"

        try:
            r = requests.get(url, headers=headers, timeout=settings.ATS_TIMEOUT_SECONDS)
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            # In production, you may want a structured error object.
            return json.dumps({"error": f"ATS fetch failed: {str(e)}"})

        # Mapping example (adjust to match your ATS response keys)
        jr = JobRequisitionRaw(
            req_id=requisition_number,
            title=payload.get("title"),
            department=payload.get("department"),
            location=payload.get("location"),
            jd_text=payload.get("job_description") or payload.get("jd_text") or "",
            metadata={"raw": payload},
        )
        return jr.model_dump_json()
```

---

## app/**init**.py

```python
# Keeps app importable.
```

---

## app/db/**init**.py, app/schemas/**init**.py, app/tools/**init**.py

```python
# empty init files
```

---

## run_smoke_test.py (verify DB wiring quickly)

This runs without CrewAI, purely to confirm you can connect + pull a small sample.

```python
import json

from app.db.repository import RecruitmentRepository
from app.schemas.search import CandidateSearchFilters


def main():
    repo = RecruitmentRepository()

    # 1) Quick search (first 5 candidates)
    filters = CandidateSearchFilters(limit=5, offset=0)
    resp = repo.search_candidates(filters)
    ids = [r.candidate_id for r in resp.results]
    print("Candidate IDs:", ids)

    # 2) Fetch profiles for those ids
    profiles = repo.get_candidate_profiles(ids)
    print("Profiles fetched:", len(profiles))
    print(json.dumps([p.model_dump() for p in profiles[:1]], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

---

# What you must edit before running

### 1) Update column maps to your real schema

In `app/db/repository.py`, update:

* `COLUMN_MAP_CANDIDATE`
* `COLUMN_MAP_EDU`
* `COLUMN_MAP_EXP`
* `COLUMN_MAP_SKL`

If you paste me **one row of each table’s column list** (or a screenshot of SSMS “Design” view), I can rewrite the maps precisely.

### 2) Set your DB connection settings

Create `.env` at repo root:

```env
DB_DRIVER={ODBC Driver 17 for SQL Server}
DB_SERVER=cw-002918
DB_NAME=arif_recruitment
DB_TRUSTED_CONNECTION=yes
```

(If you use SQL auth instead: set `DB_TRUSTED_CONNECTION=no`, `DB_USERNAME`, `DB_PASSWORD`.)

---

# What Step 1 gives you (guarantees)

* **Parameterised queries** (no string injection)
* Deterministic retrieval from your four tables
* CrewAI tools that return:

  * candidate IDs from search filters
  * full joined profiles for selected candidates
* ATS tool placeholder with **required output contract** for downstream steps

---

# Next (Step 2)

Step 2 will add:

* **Session memory table** (SQL) + state machine scaffolding
* `SessionMemoryTool` (read/write state_json)
* Orchestrator skeleton that supports multi-turn clarification

If you want, I can also include a small helper script to **auto-discover column names** from SQL Server (`INFORMATION_SCHEMA.COLUMNS`) so you don’t have to manually map columns.
