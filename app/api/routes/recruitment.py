from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.repository import RecruitmentRepository
from app.orchestration.recruitment_flow import RecruitmentFlow
from app.schemas.memory import ClarificationAnswer
from app.schemas.requisition import JobRequisitionRaw
from app.services.orchestrator_state import RecruitmentSessionManager

router = APIRouter(prefix="", tags=["recruitment"])
_flow = RecruitmentFlow()
_session_manager = RecruitmentSessionManager()
_repo = RecruitmentRepository()


class RequisitionIngestRequest(BaseModel):
    session_id: str | None = None
    requisition_id: str | None = None
    title: str | None = None
    department: str | None = None
    location: str | None = None
    jd_text: str = Field(..., min_length=20)


class ClarifyRequest(BaseModel):
    session_id: str
    answers: list[ClarificationAnswer]


class SearchRequest(BaseModel):
    session_id: str


class FeedbackRequest(BaseModel):
    session_id: str
    candidate_id: str | None = None
    verdict: str = Field(..., description="thumbs_up | thumbs_down | note")
    note: str | None = None


@router.post("/requisition/ingest")
def requisition_ingest(payload: RequisitionIngestRequest) -> dict:
    requisition_id = payload.requisition_id or f"JR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    session_id = payload.session_id or f"sess-{uuid4().hex[:10]}"

    requisition = JobRequisitionRaw(
        req_id=requisition_id,
        title=payload.title,
        department=payload.department,
        location=payload.location,
        jd_text=payload.jd_text,
        metadata={"source": "api"},
    )

    result = _flow.start(session_id=session_id, requisition=requisition)
    response = result.model_dump()
    response["requisition_id"] = requisition_id
    response["session_id"] = session_id
    return response


@router.post("/requisition/{requisition_id}/clarify")
def requisition_clarify(requisition_id: str, payload: ClarifyRequest) -> dict:
    state = _session_manager.get(payload.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if state.requisition_id and state.requisition_id != requisition_id:
        raise HTTPException(status_code=400, detail="Session/requisition mismatch")

    result = _flow.resume_with_answers(session_id=payload.session_id, answers=payload.answers)
    return result.model_dump()


@router.post("/search")
def search(payload: SearchRequest) -> dict:
    state = _session_manager.get(payload.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    ranked = state.state.get("ranked_candidates")
    if ranked:
        return {
            "session_id": payload.session_id,
            "requisition_id": state.requisition_id,
            "count": len(ranked),
            "ranked_candidates": ranked,
            "archetype_report": state.state.get("archetype_report"),
        }

    questions = state.state.get("clarification_questions")
    if questions:
        return {
            "session_id": payload.session_id,
            "requisition_id": state.requisition_id,
            "status": "needs_clarification",
            "clarification_questions": questions,
        }

    return {
        "session_id": payload.session_id,
        "requisition_id": state.requisition_id,
        "status": "not_ready",
        "message": "No search results available yet. Ingest requisition first.",
    }


@router.get("/candidate/{candidate_id}")
def candidate_details(candidate_id: str) -> dict:
    profiles = _repo.get_candidate_profiles([candidate_id])
    if not profiles:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"candidate": profiles[0].model_dump()}


@router.post("/feedback")
def feedback(payload: FeedbackRequest) -> dict:
    # Placeholder endpoint for v1. Persist to DB/audit table in the next step.
    return {
        "status": "accepted",
        "session_id": payload.session_id,
        "candidate_id": payload.candidate_id,
        "verdict": payload.verdict,
        "note": payload.note,
    }
