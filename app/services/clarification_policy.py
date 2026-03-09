from __future__ import annotations

import re

from app.schemas.memory import ClarificationAnswer, ClarificationQuestion
from app.schemas.requirements import JobRequirements, SkillRequirement


QUESTION_BANK: dict[str, tuple[str, str, str]] = {
    "must_have_skills": (
        "q_must_have_skills",
        "List the mandatory technical skills (comma separated, 3 to 7 items).",
        "This separates specialist profiles from broad generalists.",
    ),
    "experience.min_years_relevant": (
        "q_min_years_relevant",
        "What is the minimum relevant production ML experience in years?",
        "This sets the minimum seniority threshold for retrieval.",
    ),
    "work_constraints.location": (
        "q_location",
        "What location constraint should be applied (city/country/remote)?",
        "Location is a hard filter and can strongly shrink/expand the pool.",
    ),
    "education.min_level": (
        "q_education_level",
        "What is the minimum education level (Bachelor/Master/PhD)?",
        "This controls strictness and can remove otherwise strong industry profiles.",
    ),
}


class ClarificationPolicy:
    """Generates impact-first questions and applies answers to schema fields."""

    def generate(self, requirements: JobRequirements, max_questions: int = 7) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []
        seen_ids: set[str] = set()

        for field in requirements.missing_fields:
            if field not in QUESTION_BANK:
                continue
            qid, prompt, tradeoff = QUESTION_BANK[field]
            if qid in seen_ids:
                continue
            seen_ids.add(qid)
            questions.append(
                ClarificationQuestion(
                    question_id=qid,
                    prompt=prompt,
                    target_field=field,
                    tradeoff_note=tradeoff,
                )
            )

        return questions[:max_questions]

    def apply_answers(self, requirements: JobRequirements, answers: list[ClarificationAnswer]) -> JobRequirements:
        updated = requirements.model_copy(deep=True)

        for answer in answers:
            raw = answer.answer.strip()
            if not raw:
                continue

            if answer.question_id == "q_must_have_skills":
                skills = [s.strip().lower() for s in raw.split(",") if s.strip()]
                updated.must_have_skills = [SkillRequirement(skill=s, weight=1.0) for s in skills]
            elif answer.question_id == "q_min_years_relevant":
                years = self._extract_float(raw)
                if years is not None:
                    updated.experience.min_years_relevant = years
                    if updated.experience.min_years_total is None:
                        updated.experience.min_years_total = years
            elif answer.question_id == "q_location":
                updated.work_constraints.location = raw
            elif answer.question_id == "q_education_level":
                normalized = raw.lower()
                if "phd" in normalized:
                    updated.education.min_level = "phd"
                elif "master" in normalized:
                    updated.education.min_level = "master"
                elif "bachelor" in normalized:
                    updated.education.min_level = "bachelor"

        updated.missing_fields = self._recompute_missing_fields(updated)
        if not updated.missing_fields:
            updated.confidence = min(1.0, max(updated.confidence, 0.8))
        else:
            updated.confidence = min(1.0, max(updated.confidence, 0.6))
        return updated

    def _recompute_missing_fields(self, requirements: JobRequirements) -> list[str]:
        missing: list[str] = []
        if not requirements.must_have_skills:
            missing.append("must_have_skills")
        if requirements.experience.min_years_relevant is None:
            missing.append("experience.min_years_relevant")
        if not requirements.work_constraints.location:
            missing.append("work_constraints.location")
        if requirements.education.min_level is None:
            missing.append("education.min_level")
        return missing

    def _extract_float(self, raw: str) -> float | None:
        match = re.search(r"\d+(?:\.\d+)?", raw)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None
