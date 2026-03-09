from __future__ import annotations

from pydantic import BaseModel, Field


class SkillRequirement(BaseModel):
    skill: str
    min_years: float | None = None
    weight: float = 1.0


class EducationRequirement(BaseModel):
    min_level: str | None = None
    preferred_majors: list[str] = Field(default_factory=list)
    min_gpa: float | None = None


class ExperienceRequirement(BaseModel):
    min_years_total: float | None = None
    min_years_relevant: float | None = None
    required_titles: list[str] = Field(default_factory=list)


class WorkConstraints(BaseModel):
    location: str | None = None
    onsite_policy: str | None = None
    language: str | None = None
    authorization: str | None = None


class ScoringPreferences(BaseModel):
    weight_skills: float = 0.45
    weight_title_fit: float = 0.2
    weight_domain: float = 0.15
    weight_scores: float = 0.1
    weight_education: float = 0.1


class JobRequirements(BaseModel):
    role_title: str | None = None
    seniority: str | None = None
    must_have_skills: list[SkillRequirement] = Field(default_factory=list)
    nice_to_have_skills: list[SkillRequirement] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    education: EducationRequirement = Field(default_factory=EducationRequirement)
    experience: ExperienceRequirement = Field(default_factory=ExperienceRequirement)
    work_constraints: WorkConstraints = Field(default_factory=WorkConstraints)
    scoring_preferences: ScoringPreferences = Field(default_factory=ScoringPreferences)
    exclusions: dict = Field(default_factory=dict)
    confidence: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
