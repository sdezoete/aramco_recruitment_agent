from __future__ import annotations

import re

from app.schemas.requirements import JobRequirements, SkillRequirement
from app.schemas.requisition import JobRequisitionRaw

SENIORITY_MAP = {
    "lead": "lead",
    "principal": "lead",
    "senior": "senior",
    "mid": "mid",
    "junior": "junior",
}

SKILL_HINTS = [
    "python",
    "pytorch",
    "tensorflow",
    "mlops",
    "kubernetes",
    "docker",
    "sql",
    "nlp",
    "computer vision",
    "mlflow",
    "azure",
    "aws",
]


class RequirementsAnalystAgent:
    """Rule-first extraction to avoid invented fields in early MVP."""

    def run(self, requisition: JobRequisitionRaw) -> JobRequirements:
        text = requisition.jd_text.lower()
        requirements = JobRequirements(role_title=requisition.title, confidence=0.55)

        for key, value in SENIORITY_MAP.items():
            if key in text:
                requirements.seniority = value
                break

        years_match = re.search(r"(\d{1,2})\+?\s+years", text)
        if years_match:
            requirements.experience.min_years_total = float(years_match.group(1))
            requirements.experience.min_years_relevant = float(years_match.group(1))
            requirements.confidence += 0.1

        for skill in SKILL_HINTS:
            if skill in text:
                requirements.must_have_skills.append(SkillRequirement(skill=skill))

        if "oil" in text and "gas" in text:
            requirements.domain_keywords.append("oil and gas")
        if "finance" in text:
            requirements.domain_keywords.append("finance")

        if requisition.location:
            requirements.work_constraints.location = requisition.location

        if "bachelor" in text:
            requirements.education.min_level = "bachelor"
        if "master" in text:
            requirements.education.min_level = "master"
        if "phd" in text:
            requirements.education.min_level = "phd"

        missing: list[str] = []
        if not requirements.must_have_skills:
            missing.append("must_have_skills")
        if requirements.experience.min_years_relevant is None:
            missing.append("experience.min_years_relevant")
        if not requirements.work_constraints.location:
            missing.append("work_constraints.location")
        requirements.missing_fields = missing

        if not missing:
            requirements.confidence += 0.2
        return requirements
