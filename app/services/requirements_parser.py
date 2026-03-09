from __future__ import annotations

import re
from typing import Any

from app.schemas.requirements import JobRequirements, SkillRequirement
from app.schemas.requisition import JobRequisitionRaw
from app.services.llm import LLMService


class RequirementsParser:
    """LLM-first parser with deterministic fallback for resilience."""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def parse(self, requisition: JobRequisitionRaw) -> JobRequirements:
        try:
            payload = self.llm_service.extract_job_requirements(
                job_text=requisition.jd_text,
                role_title=requisition.title,
                location=requisition.location,
            )
            normalized = self._normalize_payload(payload, requisition)
            return JobRequirements(**normalized)
        except Exception:
            # Fallback stays generic and non-role-specific.
            return self._fallback_parse(requisition)

    def _normalize_payload(self, payload: dict[str, Any], requisition: JobRequisitionRaw) -> dict[str, Any]:
        data = dict(payload)

        data.setdefault("role_title", requisition.title)
        data.setdefault("must_have_skills", [])
        data.setdefault("nice_to_have_skills", [])
        data.setdefault("domain_keywords", [])
        data.setdefault("education", {})
        data.setdefault("experience", {})
        data.setdefault("work_constraints", {})
        data.setdefault("scoring_preferences", {})
        data.setdefault("exclusions", {})
        data.setdefault("missing_fields", [])

        wc = data["work_constraints"]
        if not wc.get("location") and requisition.location:
            wc["location"] = requisition.location

        data["confidence"] = float(data.get("confidence", 0.6))
        data["confidence"] = min(1.0, max(0.0, data["confidence"]))

        data["missing_fields"] = self._compute_missing_fields(data)

        data["must_have_skills"] = [self._normalize_skill(item, default_weight=1.0) for item in data["must_have_skills"]]
        data["nice_to_have_skills"] = [self._normalize_skill(item, default_weight=0.6) for item in data["nice_to_have_skills"]]

        return data

    def _normalize_skill(self, item: Any, default_weight: float) -> dict[str, Any]:
        if isinstance(item, str):
            return {"skill": item.strip().lower(), "min_years": None, "weight": default_weight}
        if not isinstance(item, dict):
            return {"skill": "unknown", "min_years": None, "weight": default_weight}
        return {
            "skill": str(item.get("skill", "unknown")).strip().lower(),
            "min_years": item.get("min_years"),
            "weight": float(item.get("weight", default_weight)),
        }

    def _compute_missing_fields(self, data: dict[str, Any]) -> list[str]:
        missing: list[str] = []

        if not data.get("must_have_skills"):
            missing.append("must_have_skills")

        exp = data.get("experience", {}) or {}
        if exp.get("min_years_relevant") is None:
            missing.append("experience.min_years_relevant")

        work = data.get("work_constraints", {}) or {}
        if not work.get("location"):
            missing.append("work_constraints.location")

        edu = data.get("education", {}) or {}
        if not edu.get("min_level"):
            missing.append("education.min_level")

        return missing

    def _fallback_parse(self, requisition: JobRequisitionRaw) -> JobRequirements:
        text = (requisition.jd_text or "").lower()
        req = JobRequirements(role_title=requisition.title, confidence=0.45)

        years_match = re.search(r"(\d{1,2})\s*\+?\s*(years|yrs)", text)
        if years_match:
            years = float(years_match.group(1))
            req.experience.min_years_total = years
            req.experience.min_years_relevant = years

        if "phd" in text or "doctorate" in text:
            req.education.min_level = "phd"
        elif "master" in text:
            req.education.min_level = "master"
        elif "bachelor" in text:
            req.education.min_level = "bachelor"

        if requisition.location:
            req.work_constraints.location = requisition.location

        skill_candidates = self._extract_skill_candidates(text)
        req.must_have_skills = [SkillRequirement(skill=s, weight=1.0) for s in skill_candidates]

        req.missing_fields = self._compute_missing_fields(req.model_dump())
        if not req.missing_fields:
            req.confidence = 0.7
        return req

    def _extract_skill_candidates(self, text: str) -> list[str]:
        patterns = [
            r"must have[:\s]+([^\.\n]+)",
            r"required skills?[:\s]+([^\.\n]+)",
            r"experience with[:\s]+([^\.\n]+)",
        ]
        skills: list[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text):
                for token in re.split(r",|/| and ", match):
                    t = token.strip().lower()
                    if 2 < len(t) <= 40 and t not in {"etc", "tools", "technologies"}:
                        skills.append(t)

        deduped: list[str] = []
        seen: set[str] = set()
        for skill in skills:
            if skill in seen:
                continue
            seen.add(skill)
            deduped.append(skill)
        return deduped[:10]
