from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SessionState(BaseModel):
    session_id: str
    requisition_id: str | None = None
    state: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionPatch(BaseModel):
    """Partial state payload to merge into existing session state."""

    state: dict = Field(default_factory=dict)


class ClarificationQuestion(BaseModel):
    question_id: str
    prompt: str
    target_field: str
    tradeoff_note: str


class ClarificationAnswer(BaseModel):
    question_id: str
    answer: str
