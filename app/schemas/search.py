from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateSearchFilters(BaseModel):
    candidate_ids: list[str] | None = None
    skills_any: list[str] | None = None
    skills_all: list[str] | None = None
    text_keywords_any: list[str] | None = None
    min_gpa: float | None = None
    degree_levels_any: list[str] | None = None
    majors_any: list[str] | None = None
    min_test_verbal: float | None = None
    min_test_math: float | None = None
    min_test_insight: float | None = None
    limit: int = 50
    offset: int = 0


class CandidateSearchResult(BaseModel):
    candidate_id: str
    score_hint: float | None = Field(default=None)
    reasons: list[str] = Field(default_factory=list)


class CandidateSearchResponse(BaseModel):
    total_estimated: int | None = None
    results: list[CandidateSearchResult]
