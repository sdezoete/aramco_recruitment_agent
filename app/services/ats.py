from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from app.config import settings
from app.db.connection import open_db_connection
from app.services import ats_api


def get_job_requisitions_for_recruiter(recruiter_id: str = "current_user") -> dict[str, Any]:
    """Return requisitions for a recruiter in ATS-like JSON format."""
    if not settings.ATS_USE_MOCK:
        reqs = ats_api.fetch_job_requisitions_for_recruiter(recruiter_id)
        return {"recruiter_id": recruiter_id, "count": len(reqs), "job_requisitions": reqs}

    reqs = [
        {
            "requisition_id": "JR-1001",
            "title": "Data Scientist",
            "department": "AI",
            "location": "Dhahran",
            "status": "Open",
        },
        {
            "requisition_id": "JR-1002",
            "title": "AI Engineer",
            "department": "AI Platform",
            "location": "Riyadh",
            "status": "Open",
        },
        {
            "requisition_id": "JR-1003",
            "title": "Generative AI Specialist",
            "department": "Innovation",
            "location": "Jeddah",
            "status": "Open",
        },
    ]
    return {"recruiter_id": recruiter_id, "count": len(reqs), "job_requisitions": reqs}


def get_applications_for_requisition(requisition_id: str, limit: int = 20) -> dict[str, Any]:
    """Return requisition applications in ATS-like JSON format.

    Mock mode selects random candidates from local database.
    """
    if not settings.ATS_USE_MOCK:
        apps = ats_api.fetch_applications_for_requisition(requisition_id)
        return {"requisition_id": requisition_id, "count": len(apps), "applications": apps}

    safe_limit = max(1, min(int(limit), 200))

    sql = f"""
    SELECT TOP {safe_limit}
        CANDIDATE_ID,
        ARIF_ID,
        GIVENNAME,
        SURNAME,
        CURRENT_JOB_TITLE,
        CREATED_ON,
        HIGHEST_APPLICATION_STATUS
    FROM dbo.T_IIR_ARIF_CANDIDATE
    ORDER BY NEWID();
    """

    applications: list[dict[str, Any]] = []
    with open_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()

    for idx, row in enumerate(rows, start=1):
        candidate_id = int(row[0])
        arif_id = int(row[1])
        given_name = row[2] or ""
        surname = row[3] or ""
        job_title = row[4]
        created_on = row[5]
        status = row[6] or "Application Review"

        applications.append(
            {
                "application_id": f"APP-{requisition_id}-{idx:04d}",
                "requisition_id": requisition_id,
                "candidate_id": candidate_id,
                "arif_id": arif_id,
                "candidate_name": f"{given_name} {surname}".strip(),
                "current_job_title": job_title,
                "applied_on": _to_iso_date(created_on),
                "status": status,
            }
        )

    return {
        "requisition_id": requisition_id,
        "count": len(applications),
        "applications": applications,
    }


def get_candidate_information(candidate_id: int) -> dict[str, Any]:
    """Return candidate profile from ATS candidate payload (table fields only)."""
    if not settings.ATS_USE_MOCK:
        return ats_api.fetch_candidate_information(candidate_id)

    sql = """
    SELECT TOP 1
        ARIF_ID,
        CANDIDATE_ID,
        GIVENNAME,
        MIDDLENAME,
        SURNAME,
        CREATED_ON,
        CURRENT_EMPLOYER,
        CURRENT_JOB_TITLE,
        YEARS_OF_EXPERIENCE,
        COUNTRY,
        NATIONAL_ID,
        SAUDI_EXPAT,
        GPA,
        LAST_MODIFIED,
        SOURCE_OF_APPLICATION,
        GENDER,
        HIGHEST_JOB_REQ_ID,
        HIGHEST_APPLICATION_ID,
        HIGHEST_APPLICATION_STATUS,
        APPLICATION_STATUS_CODE,
        RESUME_UPLOADED,
        RESUME_DATE,
        RESUME_FILE_TYPE,
        RESUME_PROCESSED,
        EDUCATION_EXTRACTED,
        EXPERIENCE_EXTRACTED,
        SKILLS_EXTRACTED,
        SUMMARY_EXTRACTED,
        WILD_SEARCH_EXTRACTED,
        CANDIDATE_FLAG,
        INDREASON,
        NUMREASON,
        VERBREASON,
        SUMMARY,
        TEXT_TOKENS
    FROM dbo.T_IIR_ARIF_CANDIDATE
    WHERE CANDIDATE_ID = ?;
    """

    with open_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, (candidate_id,))
        row = cur.fetchone()
        if not row:
            return {"found": False, "candidate_id": candidate_id}

    cols = [
        "ARIF_ID",
        "CANDIDATE_ID",
        "GIVENNAME",
        "MIDDLENAME",
        "SURNAME",
        "CREATED_ON",
        "CURRENT_EMPLOYER",
        "CURRENT_JOB_TITLE",
        "YEARS_OF_EXPERIENCE",
        "COUNTRY",
        "NATIONAL_ID",
        "SAUDI_EXPAT",
        "GPA",
        "LAST_MODIFIED",
        "SOURCE_OF_APPLICATION",
        "GENDER",
        "HIGHEST_JOB_REQ_ID",
        "HIGHEST_APPLICATION_ID",
        "HIGHEST_APPLICATION_STATUS",
        "APPLICATION_STATUS_CODE",
        "RESUME_UPLOADED",
        "RESUME_DATE",
        "RESUME_FILE_TYPE",
        "RESUME_PROCESSED",
        "EDUCATION_EXTRACTED",
        "EXPERIENCE_EXTRACTED",
        "SKILLS_EXTRACTED",
        "SUMMARY_EXTRACTED",
        "WILD_SEARCH_EXTRACTED",
        "CANDIDATE_FLAG",
        "INDREASON",
        "NUMREASON",
        "VERBREASON",
        "SUMMARY",
        "TEXT_TOKENS",
    ]
    payload = dict(zip(cols, row))

    resume_path = Path(settings.ATS_RESUME_STORAGE_PATH) / f"{candidate_id}.pdf"

    return {
        "found": True,
        "candidate_id": candidate_id,
        "candidate": _serialize_dates(payload),
        "resume": {
            "storage_path": str(resume_path),
            "file_exists": resume_path.exists(),
            "source": "configured_resume_storage",
        },
    }


def _to_iso_date(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value is not None else None


def _serialize_dates(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, date):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out
