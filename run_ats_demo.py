from __future__ import annotations

import json

from app.services.ats import (
    get_applications_for_requisition,
    get_candidate_information,
    get_job_requisitions_for_recruiter,
)


def main() -> None:
    reqs = get_job_requisitions_for_recruiter("current_user")
    print("job_requisitions:")
    print(json.dumps(reqs, indent=2, ensure_ascii=True))

    requisition_id = reqs["job_requisitions"][0]["requisition_id"]
    applications = get_applications_for_requisition(requisition_id, limit=20)
    print("applications:")
    print(json.dumps(applications, indent=2, ensure_ascii=True))

    first_candidate_id = applications["applications"][0]["candidate_id"] if applications["applications"] else None
    if first_candidate_id is not None:
        candidate = get_candidate_information(first_candidate_id)
        print("candidate_information:")
        print(json.dumps(candidate, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
