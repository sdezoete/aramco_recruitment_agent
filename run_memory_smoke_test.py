from __future__ import annotations

import json

from app.services.orchestrator_state import RecruitmentSessionManager, WorkflowState


def main() -> None:
    manager = RecruitmentSessionManager()

    state = manager.initialize("demo-session", requisition_id="JR-0001")
    print("initialized:", json.dumps(state.model_dump(), indent=2, ensure_ascii=True))

    state = manager.transition(
        "demo-session",
        WorkflowState.PARSED,
        extra_state={
            "requirements_confidence": 0.78,
            "missing_fields": ["work_constraints.location", "experience.min_years_relevant"],
        },
    )
    print("transitioned:", json.dumps(state.model_dump(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
