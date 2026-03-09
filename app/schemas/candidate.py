from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateCore(BaseModel):
    candidate_id: str = Field(..., description="Primary candidate identifier")
    full_name: str | None = None
    email: str | None = None
    summary: str | None = None
    resume_text_dump: str | None = None
    test_score_verbal: float | None = None
    test_score_math: float | None = None
    test_score_insight: float | None = None
    current_title: str | None = None
    current_employer: str | None = None
    location: str | None = None


class EducationRow(BaseModel):
    candidate_id: str
    degree_level: str | None = None
    major: str | None = None
    institution: str | None = None
    gpa: float | None = None
    start_date: str | None = None
    end_date: str | None = None


class ExperienceRow(BaseModel):
    candidate_id: str
    job_title: str | None = None
    employer: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class SkillRow(BaseModel):
    candidate_id: str
    skill: str
    proficiency: str | None = None
    years: float | None = None
    last_used: str | None = None


class CandidateProfile(BaseModel):
    candidate: CandidateCore
    education: list[EducationRow] = Field(default_factory=list)
    experience: list[ExperienceRow] = Field(default_factory=list)
    skills: list[SkillRow] = Field(default_factory=list)
