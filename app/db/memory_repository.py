from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.connection import open_db_connection
from app.schemas.memory import SessionState


class SessionMemoryRepository:
    """SQL-backed persistence for AGENT_SESSION_MEMORY."""

    table_name = "AGENT_SESSION_MEMORY"

    def upsert(self, session_state: SessionState) -> SessionState:
        now = datetime.now(timezone.utc).isoformat()
        state_json = json.dumps(session_state.state, ensure_ascii=True)

        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                MERGE {self.table_name} AS target
                USING (SELECT ? AS session_id) AS source
                ON target.session_id = source.session_id
                WHEN MATCHED THEN
                    UPDATE SET
                        requisition_id = ?,
                        state_json = ?,
                        updated_at = SYSUTCDATETIME()
                WHEN NOT MATCHED THEN
                    INSERT (session_id, requisition_id, state_json, created_at, updated_at)
                    VALUES (?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME());
                """,
                (
                    session_state.session_id,
                    session_state.requisition_id,
                    state_json,
                    session_state.session_id,
                    session_state.requisition_id,
                    state_json,
                ),
            )

        session_state.updated_at = now
        if not session_state.created_at:
            session_state.created_at = now
        return session_state

    def get(self, session_id: str) -> SessionState | None:
        with open_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT session_id, requisition_id, state_json,
                       CONVERT(varchar(33), created_at, 126) AS created_at,
                       CONVERT(varchar(33), updated_at, 126) AS updated_at
                FROM {self.table_name}
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return SessionState(
            session_id=row[0],
            requisition_id=row[1],
            state=json.loads(row[2]) if row[2] else {},
            created_at=row[3],
            updated_at=row[4],
        )
