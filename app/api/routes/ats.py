from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.services.ats import (
    get_applications_for_requisition,
    get_candidate_information,
    get_job_requisitions_for_recruiter,
)

router = APIRouter(prefix="/ats", tags=["ats"])


@router.get("/requisitions")
def ats_requisitions(recruiter_id: str = "current_user") -> dict:
    return get_job_requisitions_for_recruiter(recruiter_id=recruiter_id)


@router.get("/requisitions/{requisition_id}/applications")
def ats_requisition_applications(requisition_id: str, limit: int = 20) -> dict:
    return get_applications_for_requisition(requisition_id=requisition_id, limit=limit)


@router.get("/candidates/{candidate_id}")
def ats_candidate(candidate_id: int) -> dict:
    return get_candidate_information(candidate_id=candidate_id)


@router.get("/candidates/{candidate_id}/resume")
def ats_candidate_resume(candidate_id: int) -> FileResponse:
    resume_path = Path(settings.ATS_RESUME_STORAGE_PATH) / f"{candidate_id}.pdf"
    if not resume_path.exists() or not resume_path.is_file():
        raise HTTPException(status_code=404, detail="Resume file not found")
    return FileResponse(path=resume_path, media_type="application/pdf", filename=resume_path.name)


@router.get("/candidates/{candidate_id}/resume-markdown")
def ats_candidate_resume_markdown(candidate_id: int) -> dict:
    """Return mocked resume markdown from resumes/<candidate_id>.md.

    If the file does not exist yet, create a deterministic mock so every candidate can be opened.
    """
    resumes_dir = Path("resumes")
    resumes_dir.mkdir(parents=True, exist_ok=True)
    resume_md_path = resumes_dir / f"{candidate_id}.md"

    if not resume_md_path.exists():
        resume_md_path.write_text(
            "\n".join(
                [
                    f"# Candidate {candidate_id} - Mock Resume",
                    "",
                    f"Candidate ID: {candidate_id}",
                    "Location: Saudi Arabia",
                    "Email: mock.candidate@example.com",
                    "",
                    "## Summary",
                    "Machine learning and analytics profile generated for UI demo purposes.",
                    "",
                    "## Experience",
                    "- Built model pipelines in Python and SQL.",
                    "- Supported deployment and monitoring workflows.",
                    "",
                    "## Skills",
                    "Python, SQL, MLOps, Kubernetes, Data Analysis",
                    "",
                    "## Education",
                    "Bachelor in Computer Science",
                ]
            ),
            encoding="utf-8",
        )

    return {
        "candidate_id": candidate_id,
        "path": str(resume_md_path),
        "content": resume_md_path.read_text(encoding="utf-8"),
    }
