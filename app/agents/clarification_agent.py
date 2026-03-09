from __future__ import annotations

from app.schemas.memory import ClarificationAnswer, ClarificationQuestion
from app.schemas.requirements import JobRequirements, SkillRequirement


class ClarificationAgent:
    """Generates and applies bounded clarification prompts."""

    def generate(self, requirements: JobRequirements, max_questions: int = 7) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []

        for field in requirements.missing_fields:
            if field == "must_have_skills":
                questions.append(
                    ClarificationQuestion(
                        question_id="q_must_have_skills",
                        prompt="Which 3 to 5 technical skills are mandatory for shortlist eligibility?",
                        target_field="must_have_skills",
                        tradeoff_note="This determines specialist versus generalist ranking.",
                    )
                )
            elif field == "experience.min_years_relevant":
                questions.append(
                    ClarificationQuestion(
                        question_id="q_min_years_relevant",
                        prompt="What is the minimum relevant production ML experience in years?",
                        target_field="experience.min_years_relevant",
                        tradeoff_note="This controls the seniority boundary of the candidate pool.",
                    )
                )
            elif field == "work_constraints.location":
                questions.append(
                    ClarificationQuestion(
                        question_id="q_location",
                        prompt="Is there a required location, or can the role be remote/hybrid?",
                        target_field="work_constraints.location",
                        tradeoff_note="This is a hard filter and can dramatically alter pool size.",
                    )
                )

        return questions[:max_questions]

    def apply_answers(self, requirements: JobRequirements, answers: list[ClarificationAnswer]) -> JobRequirements:
        updated = requirements.model_copy(deep=True)
        for answer in answers:
            raw = answer.answer.strip()
            if answer.question_id == "q_must_have_skills":
                skills = [s.strip().lower() for s in raw.split(",") if s.strip()]
                updated.must_have_skills = [SkillRequirement(skill=s) for s in skills]
            elif answer.question_id == "q_min_years_relevant":
                try:
                    years = float(raw)
                    updated.experience.min_years_relevant = years
                    if updated.experience.min_years_total is None:
                        updated.experience.min_years_total = years
                except ValueError:
                    continue
            elif answer.question_id == "q_location":
                updated.work_constraints.location = raw

        updated.missing_fields = [
            f
            for f in updated.missing_fields
            if not (
                (f == "must_have_skills" and updated.must_have_skills)
                or (f == "experience.min_years_relevant" and updated.experience.min_years_relevant is not None)
                or (f == "work_constraints.location" and updated.work_constraints.location)
            )
        ]

        if not updated.missing_fields:
            updated.confidence = min(1.0, max(updated.confidence, 0.75))
        return updated
