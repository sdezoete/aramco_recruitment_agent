from __future__ import annotations

from typing import Any

import pyodbc

from app.db.connection import open_db_connection
from app.db.sql_builder import build_in_clause_params
from app.schemas.candidate import CandidateCore, CandidateProfile, EducationRow, ExperienceRow, SkillRow
from app.schemas.search import CandidateSearchFilters, CandidateSearchResponse, CandidateSearchResult

# Table names
T_CANDIDATE = "T_IIR_ARIF_CANDIDATE"
T_EDU = "T_IIR_ARIF_EDUCATION"
T_EXP = "T_IIR_ARIF_EXPERIENCE"
T_SKL = "T_IIR_ARIF_SKILLS"

# Update right-hand values if your real SQL column names differ.
COLUMN_MAP_CANDIDATE = {
    "candidate_id": "CAST(CANDIDATE_ID AS NVARCHAR(64))",
    "full_name": "LTRIM(RTRIM(CONCAT(COALESCE(GIVENNAME, ''), ' ', COALESCE(MIDDLENAME, ''), ' ', COALESCE(SURNAME, ''))))",
    "email": "NULL",
    "summary": "SUMMARY",
    "resume_text_dump": "TEXT_TOKENS",
    "test_score_verbal": "TRY_CAST(VERBREASON AS FLOAT)",
    "test_score_math": "TRY_CAST(NUMREASON AS FLOAT)",
    "test_score_insight": "TRY_CAST(INDREASON AS FLOAT)",
    "current_title": "CURRENT_JOB_TITLE",
    "current_employer": "CURRENT_EMPLOYER",
    "location": "COUNTRY",
}

COLUMN_MAP_EDU = {
    "candidate_id": "CAST(CANDIDATE_ID AS NVARCHAR(64))",
    "degree_level": "DEGREE",
    "major": "MAJOR",
    "institution": "INSTITUTION",
    "gpa": "NULL",
    "start_date": "STARTDATE",
    "end_date": "ENDDATE",
}

COLUMN_MAP_EXP = {
    "candidate_id": "CAST(CANDIDATE_ID AS NVARCHAR(64))",
    "job_title": "TITLE",
    "employer": "EMPLOYER",
    "start_date": "STARTDATE",
    "end_date": "ENDDATE",
    "description": "NULL",
}

COLUMN_MAP_SKL = {
    "candidate_id": "CAST(CANDIDATE_ID AS NVARCHAR(64))",
    "skill": "COALESCE(NORM_SKILL, ORG_SKILL)",
    "proficiency": "NULL",
    "years": "NULL",
    "last_used": "NULL",
}


def _select_list(column_map: dict[str, str]) -> str:
    return ", ".join([f"{db_col} AS {alias}" for alias, db_col in column_map.items()])


def _fetchall_dict(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    columns = [c[0] for c in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


class RecruitmentRepository:
    """Deterministic query layer for candidate data."""

    def get_candidate_core_by_ids(self, candidate_ids: list[str]) -> list[CandidateCore]:
        if not candidate_ids:
            return []

        in_clause, in_params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_CANDIDATE)}
        FROM {T_CANDIDATE}
        WHERE CANDIDATE_ID IN {in_clause}
        """

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, in_params)
            rows = _fetchall_dict(cur)

        return [CandidateCore(**row) for row in rows]

    def get_education_by_candidate_ids(self, candidate_ids: list[str]) -> list[EducationRow]:
        if not candidate_ids:
            return []

        in_clause, in_params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_EDU)}
        FROM {T_EDU}
        WHERE CANDIDATE_ID IN {in_clause}
        """

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, in_params)
            rows = _fetchall_dict(cur)

        return [EducationRow(**row) for row in rows]

    def get_experience_by_candidate_ids(self, candidate_ids: list[str]) -> list[ExperienceRow]:
        if not candidate_ids:
            return []

        in_clause, in_params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_EXP)}
        FROM {T_EXP}
        WHERE CANDIDATE_ID IN {in_clause}
        """

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, in_params)
            rows = _fetchall_dict(cur)

        return [ExperienceRow(**row) for row in rows]

    def get_skills_by_candidate_ids(self, candidate_ids: list[str]) -> list[SkillRow]:
        if not candidate_ids:
            return []

        in_clause, in_params = build_in_clause_params(candidate_ids)
        sql = f"""
        SELECT {_select_list(COLUMN_MAP_SKL)}
        FROM {T_SKL}
        WHERE CANDIDATE_ID IN {in_clause}
        """

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, in_params)
            rows = _fetchall_dict(cur)

        return [SkillRow(**row) for row in rows]

    def get_candidate_profiles(self, candidate_ids: list[str]) -> list[CandidateProfile]:
        cores = self.get_candidate_core_by_ids(candidate_ids)
        if not cores:
            return []

        education_rows = self.get_education_by_candidate_ids(candidate_ids)
        experience_rows = self.get_experience_by_candidate_ids(candidate_ids)
        skill_rows = self.get_skills_by_candidate_ids(candidate_ids)

        edu_by_candidate: dict[str, list[EducationRow]] = {}
        for row in education_rows:
            edu_by_candidate.setdefault(row.candidate_id, []).append(row)

        exp_by_candidate: dict[str, list[ExperienceRow]] = {}
        for row in experience_rows:
            exp_by_candidate.setdefault(row.candidate_id, []).append(row)

        skills_by_candidate: dict[str, list[SkillRow]] = {}
        for row in skill_rows:
            skills_by_candidate.setdefault(row.candidate_id, []).append(row)

        profiles: list[CandidateProfile] = []
        for core in cores:
            profiles.append(
                CandidateProfile(
                    candidate=core,
                    education=edu_by_candidate.get(core.candidate_id, []),
                    experience=exp_by_candidate.get(core.candidate_id, []),
                    skills=skills_by_candidate.get(core.candidate_id, []),
                )
            )
        return profiles

    def search_candidates(self, filters: CandidateSearchFilters) -> CandidateSearchResponse:
        where_clauses: list[str] = ["1=1"]
        params: list[Any] = []

        if filters.candidate_ids:
            in_clause, in_params = build_in_clause_params(filters.candidate_ids)
            where_clauses.append(f"c.CANDIDATE_ID IN {in_clause}")
            params.extend(in_params)

        if filters.min_test_verbal is not None:
            where_clauses.append("TRY_CAST(c.VERBREASON AS FLOAT) >= ?")
            params.append(filters.min_test_verbal)
        if filters.min_test_math is not None:
            where_clauses.append("TRY_CAST(c.NUMREASON AS FLOAT) >= ?")
            params.append(filters.min_test_math)
        if filters.min_test_insight is not None:
            where_clauses.append("TRY_CAST(c.INDREASON AS FLOAT) >= ?")
            params.append(filters.min_test_insight)

        if filters.text_keywords_any:
            keyword_clauses: list[str] = []
            for keyword in filters.text_keywords_any:
                keyword_clauses.append("(c.SUMMARY LIKE ? OR c.TEXT_TOKENS LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])
            where_clauses.append("(" + " OR ".join(keyword_clauses) + ")")

        if filters.skills_any:
            in_clause, in_params = build_in_clause_params([s.lower() for s in filters.skills_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_SKL} s
                        WHERE s.CANDIDATE_ID = c.CANDIDATE_ID
                        AND LOWER(COALESCE(s.NORM_SKILL, s.ORG_SKILL)) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        if filters.skills_all:
            for skill in filters.skills_all:
                where_clauses.append(
                    f"""EXISTS (
                            SELECT 1 FROM {T_SKL} s2
                            WHERE s2.CANDIDATE_ID = c.CANDIDATE_ID
                            AND LOWER(COALESCE(s2.NORM_SKILL, s2.ORG_SKILL)) = ?
                        )"""
                )
                params.append(skill.lower())

        if filters.min_gpa is not None:
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e
                        WHERE e.CANDIDATE_ID = c.CANDIDATE_ID
                        AND TRY_CAST(c.GPA AS FLOAT) >= ?
                    )"""
            )
            params.append(filters.min_gpa)

        if filters.degree_levels_any:
            in_clause, in_params = build_in_clause_params([d.lower() for d in filters.degree_levels_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e2
                        WHERE e2.CANDIDATE_ID = c.CANDIDATE_ID
                        AND LOWER(e2.DEGREE) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        if filters.majors_any:
            in_clause, in_params = build_in_clause_params([m.lower() for m in filters.majors_any])
            where_clauses.append(
                f"""EXISTS (
                        SELECT 1 FROM {T_EDU} e3
                        WHERE e3.CANDIDATE_ID = c.CANDIDATE_ID
                        AND LOWER(e3.MAJOR) IN {in_clause}
                    )"""
            )
            params.extend(in_params)

        limit = max(1, min(filters.limit, 200))
        offset = max(0, filters.offset)

        sql = f"""
        SELECT CAST(c.CANDIDATE_ID AS NVARCHAR(64)) AS candidate_id
        FROM {T_CANDIDATE} c
        WHERE {' AND '.join(where_clauses)}
        ORDER BY c.CANDIDATE_ID
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """

        params.extend([offset, limit])

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        return CandidateSearchResponse(
            results=[CandidateSearchResult(candidate_id=str(row[0])) for row in rows]
        )
