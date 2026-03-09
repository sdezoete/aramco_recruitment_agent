from __future__ import annotations

import json

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.config import settings
from app.schemas.requisition import JobRequisitionRaw


class ATSJobToolInput(BaseModel):
    requisition_number: str = Field(..., description="ATS requisition number")


class ATSJobRequisitionTool(BaseTool):
    name: str = "ats_job_requisition_tool"
    description: str = (
        "Fetch requisition details from an internal ATS API. "
        "Replace mapping logic with your approved ATS contract."
    )
    args_schema = ATSJobToolInput

    def _run(self, requisition_number: str) -> str:
        url = f"{settings.ATS_BASE_URL}/api/requisitions/{requisition_number}"
        headers: dict[str, str] = {}
        if settings.ATS_TOKEN:
            headers["Authorization"] = f"Bearer {settings.ATS_TOKEN}"

        try:
            response = requests.get(url, headers=headers, timeout=settings.ATS_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return json.dumps({"error": f"ATS fetch failed: {exc}"}, ensure_ascii=True)

        model = JobRequisitionRaw(
            req_id=requisition_number,
            title=payload.get("title"),
            department=payload.get("department"),
            location=payload.get("location"),
            jd_text=payload.get("job_description") or payload.get("jd_text") or "",
            metadata={"raw": payload},
        )
        return model.model_dump_json()
