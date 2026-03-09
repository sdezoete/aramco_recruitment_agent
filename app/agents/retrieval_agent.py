from __future__ import annotations

from app.db.repository import RecruitmentRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.search import CandidateSearchFilters


class RetrievalAgent:
    """Deterministic retrieval over repository methods."""

    def __init__(self, repository: RecruitmentRepository | None = None) -> None:
        self.repository = repository or RecruitmentRepository()

    def run(self, filters: CandidateSearchFilters) -> list[CandidateProfile]:
        try:
            search_response = self.repository.search_candidates(filters)
            candidate_ids = [item.candidate_id for item in search_response.results]
            return self.repository.get_candidate_profiles(candidate_ids)
        except Exception:
            # Dev-safe behavior when DB connectivity is not available.
            return []
