from __future__ import annotations

import json

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.db.repository import RecruitmentRepository


class CandidateProfileToolInput(BaseModel):
    candidate_ids: list[str] = Field(..., description="Candidate IDs to fetch.")


class CandidateProfileTool(BaseTool):
    name: str = "candidate_profile_tool"
    description: str = (
        "Fetch candidate profiles including core, education, experience, and skills."
    )
    args_schema = CandidateProfileToolInput

    def _run(self, candidate_ids: list[str]) -> str:
        profiles = RecruitmentRepository().get_candidate_profiles(candidate_ids[:50])
        return json.dumps(
            {
                "count": len(profiles),
                "profiles": [profile.model_dump() for profile in profiles],
            },
            ensure_ascii=True,
        )
