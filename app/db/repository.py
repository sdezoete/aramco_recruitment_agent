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
        WHERE candidate_id IN {in_clause}
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
        WHERE candidate_id IN {in_clause}
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
        WHERE candidate_id IN {in_clause}
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
        WHERE candidate_id IN {in_clause}
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
            where_clauses.append(f"c.candidate_id IN {in_clause}")
            params.extend(in_params)

        if filters.min_test_verbal is not None:
            where_clauses.append("c.test_score_verbal >= ?")
            params.append(filters.min_test_verbal)
        if filters.min_test_math is not None:
            where_clauses.append("c.test_score_math >= ?")
            params.append(filters.min_test_math)
        if filters.min_test_insight is not None:
            where_clauses.append("c.test_score_insight >= ?")
            params.append(filters.min_test_insight)

        if filters.text_keywords_any:
            keyword_clauses: list[str] = []
            for keyword in filters.text_keywords_any:
                keyword_clauses.append("(c.summary LIKE ? OR c.resume_text_dump LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])
            where_clauses.append("(" + " OR ".join(keyword_clauses) + ")")

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
            for skill in filters.skills_all:
                where_clauses.append(
                    f"""EXISTS (
                            SELECT 1 FROM {T_SKL} s2
                            WHERE s2.candidate_id = c.candidate_id
                            AND LOWER(s2.skill) = ?
                        )"""
                )
                params.append(skill.lower())

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

        limit = max(1, min(filters.limit, 200))
        offset = max(0, filters.offset)

        sql = f"""
        SELECT c.candidate_id
        FROM {T_CANDIDATE} c
        WHERE {' AND '.join(where_clauses)}
        ORDER BY c.candidate_id
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
