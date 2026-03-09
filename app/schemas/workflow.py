from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.memory import ClarificationAnswer, ClarificationQuestion
from app.schemas.ranking import ArchetypeReport, CandidateScore


class FlowResult(BaseModel):
    status: str
    session_id: str
    requisition_id: str | None = None
    message: str | None = None
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    ranked_candidates: list[CandidateScore] = Field(default_factory=list)
    archetype_report: ArchetypeReport | None = None
    candidate_count: int | None = None


class ClarificationSubmission(BaseModel):
    session_id: str
    answers: list[ClarificationAnswer] = Field(default_factory=list)
