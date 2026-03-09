from __future__ import annotations

from typing import Any


# Production integration placeholders.
# These are intentionally not implemented in this environment.

def fetch_job_requisitions_for_recruiter(recruiter_id: str) -> list[dict[str, Any]]:
    raise NotImplementedError("Wire ATS API integration in production.")


def fetch_applications_for_requisition(requisition_id: str) -> list[dict[str, Any]]:
    raise NotImplementedError("Wire ATS API integration in production.")


def fetch_candidate_information(candidate_id: int) -> dict[str, Any]:
    raise NotImplementedError("Wire ATS API integration in production.")
