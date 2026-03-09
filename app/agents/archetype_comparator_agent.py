from __future__ import annotations

from app.schemas.candidate import CandidateProfile
from app.schemas.ranking import ArchetypeReport, ArchetypeSummary


class ArchetypeComparatorAgent:
    """Rule-based archetype grouping for Step 3 MVP."""

    def run(self, candidates: list[CandidateProfile]) -> ArchetypeReport:
        buckets: dict[str, list[str]] = {
            "Deep Learning Specialist": [],
            "MLOps Engineer": [],
            "Generalist Data Scientist": [],
        }

        for profile in candidates:
            cid = profile.candidate.candidate_id
            skills = {s.skill.lower() for s in profile.skills}

            if {"pytorch", "tensorflow", "computer vision", "nlp"}.intersection(skills):
                buckets["Deep Learning Specialist"].append(cid)
            elif {"mlops", "kubernetes", "mlflow", "docker"}.intersection(skills):
                buckets["MLOps Engineer"].append(cid)
            else:
                buckets["Generalist Data Scientist"].append(cid)

        archetypes: list[ArchetypeSummary] = []
        for name, ids in buckets.items():
            if not ids:
                continue
            if name == "Deep Learning Specialist":
                strengths = ["Model architecture depth", "Research-heavy profile"]
                risks = ["May have less production ownership"]
                best_for = "Novel model innovation"
            elif name == "MLOps Engineer":
                strengths = ["Deployment and monitoring", "Pipeline reliability"]
                risks = ["May be less focused on model architecture research"]
                best_for = "Productionization and platform reliability"
            else:
                strengths = ["Broad modeling toolkit", "Flexible domain adaptation"]
                risks = ["May lack deep specialization in one niche"]
                best_for = "Balanced experimentation and delivery"

            archetypes.append(
                ArchetypeSummary(
                    archetype_name=name,
                    candidate_ids=ids,
                    typical_strengths=strengths,
                    typical_risks=risks,
                    best_for=best_for,
                )
            )

        note = (
            "If shipping and monitoring are top priorities, favor MLOps Engineer candidates. "
            "If innovation in model quality is top priority, favor Deep Learning Specialist candidates."
        )
        return ArchetypeReport(archetypes=archetypes, recommendation_note=note)
