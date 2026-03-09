from __future__ import annotations

import json

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.schemas.memory import SessionPatch
from app.services.memory_store import SessionMemoryStore


class SessionMemoryReadInput(BaseModel):
    session_id: str = Field(..., description="Conversation/session ID")


class SessionMemoryWriteInput(BaseModel):
    session_id: str = Field(..., description="Conversation/session ID")
    requisition_id: str | None = Field(default=None)
    patch_json: str = Field(..., description="JSON object merged into state_json")


class SessionMemoryReadTool(BaseTool):
    name: str = "session_memory_read_tool"
    description: str = "Read persisted session state by session_id."
    args_schema = SessionMemoryReadInput

    def _run(self, session_id: str) -> str:
        store = SessionMemoryStore()
        state = store.get(session_id)
        if state is None:
            return json.dumps({"found": False, "session_id": session_id}, ensure_ascii=True)
        return json.dumps({"found": True, "state": state.model_dump()}, ensure_ascii=True)


class SessionMemoryWriteTool(BaseTool):
    name: str = "session_memory_write_tool"
    description: str = "Upsert session state patch into AGENT_SESSION_MEMORY or file backend."
    args_schema = SessionMemoryWriteInput

    def _run(self, session_id: str, patch_json: str, requisition_id: str | None = None) -> str:
        store = SessionMemoryStore()
        patch = SessionPatch(state=json.loads(patch_json))
        saved = store.patch(session_id=session_id, patch=patch, requisition_id=requisition_id)
        return json.dumps({"ok": True, "state": saved.model_dump()}, ensure_ascii=True)
