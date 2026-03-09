from __future__ import annotations

from app.agents.archetype_comparator_agent import ArchetypeComparatorAgent
from app.agents.clarification_agent import ClarificationAgent
from app.agents.intake_agent import IntakeAgent
from app.agents.ranker_explainer_agent import RankerExplainerAgent
from app.agents.requirements_analyst_agent import RequirementsAnalystAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.search_planner_agent import SearchPlannerAgent
from app.schemas.candidate import CandidateProfile
from app.schemas.memory import ClarificationAnswer, ClarificationQuestion
from app.schemas.planning import QueryPlan
from app.schemas.ranking import ArchetypeReport, CandidateScore
from app.schemas.requirements import JobRequirements
from app.schemas.requisition import JobRequisitionRaw
from app.schemas.search import CandidateSearchFilters


class RecruitmentTasks:
    """Thin task layer that composes deterministic Step 3 agents."""

    def __init__(self) -> None:
        self.intake_agent = IntakeAgent()
        self.requirements_agent = RequirementsAnalystAgent()
        self.clarifier_agent = ClarificationAgent()
        self.search_planner_agent = SearchPlannerAgent()
        self.retrieval_agent = RetrievalAgent()
        self.ranker_agent = RankerExplainerAgent()
        self.archetype_agent = ArchetypeComparatorAgent()

    def intake(self, requisition: JobRequisitionRaw) -> JobRequisitionRaw:
        return self.intake_agent.run(requisition)

    def parse_requirements(self, requisition: JobRequisitionRaw) -> JobRequirements:
        return self.requirements_agent.run(requisition)

    def generate_clarification_questions(self, requirements: JobRequirements) -> list[ClarificationQuestion]:
        return self.clarifier_agent.generate(requirements=requirements)

    def apply_clarification_answers(
        self,
        requirements: JobRequirements,
        answers: list[ClarificationAnswer],
    ) -> JobRequirements:
        return self.clarifier_agent.apply_answers(requirements=requirements, answers=answers)

    def create_search_plan(self, requirements: JobRequirements) -> tuple[QueryPlan, CandidateSearchFilters]:
        return self.search_planner_agent.run(requirements=requirements)

    def retrieve_candidates(self, filters: CandidateSearchFilters) -> list[CandidateProfile]:
        return self.retrieval_agent.run(filters=filters)

    def rank_candidates(
        self,
        requirements: JobRequirements,
        candidates: list[CandidateProfile],
    ) -> list[CandidateScore]:
        return self.ranker_agent.run(requirements=requirements, candidates=candidates)

    def compare_archetypes(self, candidates: list[CandidateProfile]) -> ArchetypeReport:
        return self.archetype_agent.run(candidates=candidates)
