from __future__ import annotations

from app.schemas.requisition import JobRequisitionRaw


class IntakeAgent:
    """Normalize raw requisition input into the canonical contract."""

    def run(self, requisition: JobRequisitionRaw) -> JobRequisitionRaw:
        cleaned_text = (requisition.jd_text or "").strip()
        requisition.jd_text = cleaned_text
        return requisition
