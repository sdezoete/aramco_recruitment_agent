from __future__ import annotations

import json

from app.db.repository import RecruitmentRepository
from app.schemas.search import CandidateSearchFilters


def main() -> None:
    repo = RecruitmentRepository()

    # Step 1 smoke check: pull a small deterministic batch.
    search = repo.search_candidates(CandidateSearchFilters(limit=5, offset=0))
    ids = [item.candidate_id for item in search.results]
    print("candidate_ids:", ids)

    profiles = repo.get_candidate_profiles(ids)
    print("profile_count:", len(profiles))
    if profiles:
        print(json.dumps(profiles[0].model_dump(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
