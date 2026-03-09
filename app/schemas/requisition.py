from __future__ import annotations

from pydantic import BaseModel, Field


class JobRequisitionRaw(BaseModel):
    req_id: str = Field(..., description="Job requisition identifier")
    title: str | None = None
    department: str | None = None
    location: str | None = None
    jd_text: str = Field(..., description="Raw job description text")
    metadata: dict = Field(default_factory=dict)
