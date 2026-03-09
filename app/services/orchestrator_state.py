from __future__ import annotations

from enum import Enum

from app.schemas.memory import SessionPatch, SessionState
from app.services.memory_store import SessionMemoryStore


class WorkflowState(str, Enum):
    INGESTED = "INGESTED"
    PARSED = "PARSED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY_TO_SEARCH = "READY_TO_SEARCH"
    SEARCH_EXECUTED = "SEARCH_EXECUTED"
    RESULTS_PRESENTED = "RESULTS_PRESENTED"
    REFINED = "REFINED"


class RecruitmentSessionManager:
    """Thin orchestrator helper for state transitions + persisted session state."""

    def __init__(self, store: SessionMemoryStore | None = None) -> None:
        self.store = store or SessionMemoryStore()

    def initialize(self, session_id: str, requisition_id: str | None = None) -> SessionState:
        state = self.store.get(session_id)
        if state is None:
            state = SessionState(
                session_id=session_id,
                requisition_id=requisition_id,
                state={"workflow_state": WorkflowState.INGESTED.value},
            )
            return self.store.upsert(state)

        if requisition_id and not state.requisition_id:
            state.requisition_id = requisition_id
            self.store.upsert(state)
        return state

    def transition(self, session_id: str, new_state: WorkflowState, extra_state: dict | None = None) -> SessionState:
        patch_state = {"workflow_state": new_state.value}
        if extra_state:
            patch_state.update(extra_state)
        return self.store.patch(session_id, SessionPatch(state=patch_state))

    def get(self, session_id: str) -> SessionState | None:
        return self.store.get(session_id)
