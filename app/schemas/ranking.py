from __future__ import annotations

from pydantic import BaseModel, Field


class EvidencePointer(BaseModel):
    source: str
    detail: str


class CandidateScore(BaseModel):
    candidate_id: str
    total_score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidencePointer] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ArchetypeSummary(BaseModel):
    archetype_name: str
    candidate_ids: list[str] = Field(default_factory=list)
    typical_strengths: list[str] = Field(default_factory=list)
    typical_risks: list[str] = Field(default_factory=list)
    best_for: str | None = None


class ArchetypeReport(BaseModel):
    archetypes: list[ArchetypeSummary] = Field(default_factory=list)
    recommendation_note: str | None = None
