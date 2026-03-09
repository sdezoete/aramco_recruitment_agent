from __future__ import annotations

from app.schemas.planning import PlanFilter, QueryPlan, RankingFeature
from app.schemas.requirements import JobRequirements
from app.schemas.search import CandidateSearchFilters


class SearchPlannerAgent:
    """Translate requirement schema into a traceable query plan and DB filters."""

    def run(self, requirements: JobRequirements) -> tuple[QueryPlan, CandidateSearchFilters]:
        filters: list[PlanFilter] = []

        skills_any = [item.skill for item in requirements.must_have_skills]
        if skills_any:
            filters.append(PlanFilter(field="skills_any", operator="in", value=skills_any))

        degree = requirements.education.min_level
        if degree:
            filters.append(PlanFilter(field="degree_levels_any", operator="in", value=[degree]))

        if requirements.education.min_gpa is not None:
            filters.append(
                PlanFilter(field="min_gpa", operator=">=", value=requirements.education.min_gpa)
            )

        if requirements.experience.min_years_relevant is not None:
            filters.append(
                PlanFilter(
                    field="experience.min_years_relevant",
                    operator=">=",
                    value=requirements.experience.min_years_relevant,
                )
            )

        ranking_features = [
            RankingFeature(name="skills", weight=requirements.scoring_preferences.weight_skills),
            RankingFeature(name="title_fit", weight=requirements.scoring_preferences.weight_title_fit),
            RankingFeature(name="domain", weight=requirements.scoring_preferences.weight_domain),
            RankingFeature(name="scores", weight=requirements.scoring_preferences.weight_scores),
            RankingFeature(name="education", weight=requirements.scoring_preferences.weight_education),
        ]

        plan = QueryPlan(
            filters=filters,
            joins=["CANDIDATE", "SKILLS", "EDUCATION", "EXPERIENCE"],
            ranking_features=ranking_features,
            text_query_terms=requirements.domain_keywords,
            limit=50,
        )

        search_filters = CandidateSearchFilters(
            skills_any=skills_any or None,
            degree_levels_any=[degree] if degree else None,
            min_gpa=requirements.education.min_gpa,
            text_keywords_any=requirements.domain_keywords or None,
            limit=plan.limit,
            offset=0,
        )
        return plan, search_filters
