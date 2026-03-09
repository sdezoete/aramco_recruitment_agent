from __future__ import annotations

from app.schemas.memory import ClarificationAnswer
from app.schemas.requisition import JobRequisitionRaw
from app.schemas.requirements import JobRequirements
from app.schemas.workflow import FlowResult
from app.services.orchestrator_state import RecruitmentSessionManager, WorkflowState
from app.tasks.recruitment_tasks import RecruitmentTasks


class RecruitmentFlow:
    """Step 4 orchestration with pause/resume over persisted session state."""

    def __init__(
        self,
        tasks: RecruitmentTasks | None = None,
        session_manager: RecruitmentSessionManager | None = None,
    ) -> None:
        self.tasks = tasks or RecruitmentTasks()
        self.session_manager = session_manager or RecruitmentSessionManager()

    def start(self, session_id: str, requisition: JobRequisitionRaw) -> FlowResult:
        state = self.session_manager.initialize(session_id=session_id, requisition_id=requisition.req_id)

        ingested = self.tasks.intake(requisition)
        self.session_manager.transition(
            session_id,
            WorkflowState.INGESTED,
            extra_state={"job_requisition_raw": ingested.model_dump()},
        )

        requirements = self.tasks.parse_requirements(ingested)
        self.session_manager.transition(
            session_id,
            WorkflowState.PARSED,
            extra_state={"job_requirements": requirements.model_dump()},
        )

        if requirements.missing_fields:
            questions = self.tasks.generate_clarification_questions(requirements)
            self.session_manager.transition(
                session_id,
                WorkflowState.NEEDS_CLARIFICATION,
                extra_state={"clarification_questions": [q.model_dump() for q in questions]},
            )
            return FlowResult(
                status="needs_clarification",
                session_id=session_id,
                requisition_id=state.requisition_id or requisition.req_id,
                message="Clarification is required before search can run.",
                clarification_questions=questions,
            )

        return self._run_search_and_rank(session_id=session_id, requirements=requirements)

    def resume_with_answers(self, session_id: str, answers: list[ClarificationAnswer]) -> FlowResult:
        state = self.session_manager.get(session_id)
        if state is None:
            return FlowResult(
                status="error",
                session_id=session_id,
                message="Session not found.",
            )

        raw_requirements = state.state.get("job_requirements")
        if not raw_requirements:
            return FlowResult(
                status="error",
                session_id=session_id,
                requisition_id=state.requisition_id,
                message="No parsed requirements found in session state.",
            )

        requirements = JobRequirements(**raw_requirements)
        updated_requirements = self.tasks.apply_clarification_answers(requirements, answers)

        self.session_manager.transition(
            session_id,
            WorkflowState.READY_TO_SEARCH,
            extra_state={
                "clarification_answers": [a.model_dump() for a in answers],
                "job_requirements": updated_requirements.model_dump(),
            },
        )

        if updated_requirements.missing_fields:
            questions = self.tasks.generate_clarification_questions(updated_requirements)
            self.session_manager.transition(
                session_id,
                WorkflowState.NEEDS_CLARIFICATION,
                extra_state={"clarification_questions": [q.model_dump() for q in questions]},
            )
            return FlowResult(
                status="needs_clarification",
                session_id=session_id,
                requisition_id=state.requisition_id,
                message="Additional clarification is required.",
                clarification_questions=questions,
            )

        return self._run_search_and_rank(session_id=session_id, requirements=updated_requirements)

    def _run_search_and_rank(self, session_id: str, requirements: JobRequirements) -> FlowResult:
        plan, filters = self.tasks.create_search_plan(requirements)
        self.session_manager.transition(
            session_id,
            WorkflowState.READY_TO_SEARCH,
            extra_state={
                "search_plan": plan.model_dump(),
                "search_filters": filters.model_dump(),
            },
        )

        candidates = self.tasks.retrieve_candidates(filters)
        self.session_manager.transition(
            session_id,
            WorkflowState.SEARCH_EXECUTED,
            extra_state={
                "candidate_ids": [c.candidate.candidate_id for c in candidates],
                "candidate_count": len(candidates),
            },
        )

        ranked = self.tasks.rank_candidates(requirements, candidates)
        archetype_report = self.tasks.compare_archetypes(candidates)

        self.session_manager.transition(
            session_id,
            WorkflowState.RESULTS_PRESENTED,
            extra_state={
                "ranked_candidates": [item.model_dump() for item in ranked],
                "archetype_report": archetype_report.model_dump(),
            },
        )

        session = self.session_manager.get(session_id)
        return FlowResult(
            status="completed",
            session_id=session_id,
            requisition_id=session.requisition_id if session else None,
            ranked_candidates=ranked,
            archetype_report=archetype_report,
            candidate_count=len(candidates),
            message="Search and ranking completed.",
        )
