from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db.memory_repository import SessionMemoryRepository
from app.schemas.memory import SessionPatch, SessionState


class FileSessionMemoryStore:
    """File-backed fallback for airgapped MVP environments."""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_path = Path(base_dir or settings.SESSION_MEMORY_DIR)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe_name = session_id.replace("/", "_").replace("\\", "_")
        return self.base_path / f"{safe_name}.json"

    def get(self, session_id: str) -> SessionState | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionState(**data)

    def upsert(self, session_state: SessionState) -> SessionState:
        now = datetime.now(timezone.utc).isoformat()
        session_state.updated_at = now
        path = self._path(session_state.session_id)
        path.write_text(session_state.model_dump_json(indent=2), encoding="utf-8")
        return session_state


class SessionMemoryStore:
    """Backend selector for session memory operations."""

    def __init__(self) -> None:
        self.backend = settings.SESSION_MEMORY_BACKEND.lower().strip()
        self.sql_repo = SessionMemoryRepository()
        self.file_store = FileSessionMemoryStore()

    def get(self, session_id: str) -> SessionState | None:
        if self.backend == "file":
            return self.file_store.get(session_id)
        return self.sql_repo.get(session_id)

    def upsert(self, session_state: SessionState) -> SessionState:
        if self.backend == "file":
            return self.file_store.upsert(session_state)
        return self.sql_repo.upsert(session_state)

    def patch(self, session_id: str, patch: SessionPatch, requisition_id: str | None = None) -> SessionState:
        existing = self.get(session_id)
        if existing is None:
            existing = SessionState(session_id=session_id, requisition_id=requisition_id, state={})

        merged_state = dict(existing.state)
        merged_state.update(patch.state)
        existing.state = merged_state
        if requisition_id is not None:
            existing.requisition_id = requisition_id
        return self.upsert(existing)
