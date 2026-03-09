from __future__ import annotations

import json
import os

# Keep demo self-contained even when SQL memory table is not provisioned.
os.environ.setdefault("SESSION_MEMORY_BACKEND", "file")

from app.orchestration.recruitment_flow import RecruitmentFlow
from app.schemas.memory import ClarificationAnswer
from app.schemas.requisition import JobRequisitionRaw


def main() -> None:
    flow = RecruitmentFlow()
    session_id = "demo-flow-session"

    requisition = JobRequisitionRaw(
        req_id="JR-1001",
        title="Senior Machine Learning Engineer",
        department="AI",
        location="Dhahran",
        jd_text=(
            "We need a senior ML engineer with 5+ years experience, Python, MLOps, "
            "Kubernetes, and production model deployment in oil and gas contexts."
        ),
        metadata={"source": "demo"},
    )

    first_result = flow.start(session_id=session_id, requisition=requisition)
    print("start_result:")
    print(json.dumps(first_result.model_dump(), indent=2, ensure_ascii=True))

    if first_result.status == "needs_clarification":
        answers = [
            ClarificationAnswer(question_id="q_must_have_skills", answer="python, mlops, kubernetes"),
            ClarificationAnswer(question_id="q_min_years_relevant", answer="5"),
            ClarificationAnswer(question_id="q_location", answer="Dhahran"),
        ]
        second_result = flow.resume_with_answers(session_id=session_id, answers=answers)
        print("resume_result:")
        print(json.dumps(second_result.model_dump(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
