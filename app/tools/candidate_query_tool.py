from __future__ import annotations

import json

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.db.repository import RecruitmentRepository
from app.schemas.search import CandidateSearchFilters


class CandidateQueryToolInput(BaseModel):
    filters_json: str = Field(
        ...,
        description="JSON object string matching CandidateSearchFilters.",
    )


class CandidateQueryTool(BaseTool):
    name: str = "candidate_query_tool"
    description: str = (
        "Search candidate IDs in SQL using safe parameterized filters. "
        "Returns only IDs for downstream profile fetch."
    )
    args_schema = CandidateQueryToolInput

    def _run(self, filters_json: str) -> str:
        filters = CandidateSearchFilters(**json.loads(filters_json))
        response = RecruitmentRepository().search_candidates(filters)
        return json.dumps(
            {
                "count": len(response.results),
                "candidate_ids": [r.candidate_id for r in response.results],
            },
            ensure_ascii=True,
        )
