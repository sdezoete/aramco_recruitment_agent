from __future__ import annotations

from app.schemas.memory import ClarificationAnswer, ClarificationQuestion
from app.schemas.requirements import JobRequirements
from app.services.clarification_policy import ClarificationPolicy


class ClarificationAgent:
    """Generates and applies bounded clarification prompts."""

    def __init__(self, policy: ClarificationPolicy | None = None) -> None:
        self.policy = policy or ClarificationPolicy()

    def generate(self, requirements: JobRequirements, max_questions: int = 7) -> list[ClarificationQuestion]:
        return self.policy.generate(requirements=requirements, max_questions=max_questions)

    def apply_answers(self, requirements: JobRequirements, answers: list[ClarificationAnswer]) -> JobRequirements:
        return self.policy.apply_answers(requirements=requirements, answers=answers)
