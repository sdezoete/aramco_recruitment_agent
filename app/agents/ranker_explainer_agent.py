from __future__ import annotations

from app.schemas.candidate import CandidateProfile
from app.schemas.ranking import CandidateScore, EvidencePointer
from app.schemas.requirements import JobRequirements


class RankerExplainerAgent:
    """Simple weighted ranking with explicit evidence pointers."""

    def run(self, requirements: JobRequirements, candidates: list[CandidateProfile]) -> list[CandidateScore]:
        scores: list[CandidateScore] = []
        must_skills = {s.skill.lower() for s in requirements.must_have_skills}

        for profile in candidates:
            profile_skills = {s.skill.lower() for s in profile.skills}
            matched_skills = sorted(must_skills.intersection(profile_skills))
            skill_coverage = (len(matched_skills) / len(must_skills)) if must_skills else 0.0

            education_score = 0.0
            if requirements.education.min_level:
                for row in profile.education:
                    if (row.degree_level or "").lower() == requirements.education.min_level.lower():
                        education_score = 1.0
                        break

            domain_score = 0.0
            summary_text = (profile.candidate.summary or "").lower()
            if requirements.domain_keywords:
                hits = [k for k in requirements.domain_keywords if k.lower() in summary_text]
                domain_score = len(hits) / len(requirements.domain_keywords)

            total = (
                skill_coverage * requirements.scoring_preferences.weight_skills
                + education_score * requirements.scoring_preferences.weight_education
                + domain_score * requirements.scoring_preferences.weight_domain
            )

            evidence: list[EvidencePointer] = [
                EvidencePointer(source="SKILLS.skill", detail=f"Matched skills: {', '.join(matched_skills) or 'none'}"),
                EvidencePointer(source="CANDIDATE.summary", detail=(profile.candidate.summary or "")[:180]),
            ]

            scores.append(
                CandidateScore(
                    candidate_id=profile.candidate.candidate_id,
                    total_score=round(total, 4),
                    score_breakdown={
                        "skill_coverage": round(skill_coverage, 4),
                        "education": round(education_score, 4),
                        "domain": round(domain_score, 4),
                    },
                    evidence=evidence,
                    gaps=[] if skill_coverage >= 0.5 else ["Low must-have skill coverage"],
                )
            )

        return sorted(scores, key=lambda item: item.total_score, reverse=True)
