from __future__ import annotations

from app.schemas.requirements import JobRequirements
from app.schemas.requisition import JobRequisitionRaw
from app.services.requirements_parser import RequirementsParser


class RequirementsAnalystAgent:
    """Step 5 parser wrapper (deterministic baseline, LLM-pluggable later)."""

    def __init__(self, parser: RequirementsParser | None = None) -> None:
        self.parser = parser or RequirementsParser()

    def run(self, requisition: JobRequisitionRaw) -> JobRequirements:
        return self.parser.parse(requisition)
