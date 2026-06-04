"""AuditService — business logic for Admin AI Audit Console.

Implements all five audit panel operations:
  1. Decision log — list and detail
  2. Admin override — write user_feedback + golden dataset candidate
  3. Prompt version history and rollback
  4. Calibration dashboard (pass-through to Tier3CalibrationService)
  5. Workflow history and re-run

PLAN-F-029 TASK-003 / TASK-004 / TASK-005
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from uuid import UUID

from src.ai.decision_log.interfaces.i_ai_decision_repository import (
    IAIDecisionRepository,
)
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItemCreate
from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService
from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    UserFeedback,
    UserFeedbackCreate,
)
from src.api.admin.audit.audit_api_schemas import (
    AdminOverrideRequest,
    AdminOverrideResponse,
    AgentInvocationSummary,
    PromptVersionEntry,
    RerunRequest,
    RerunResponse,
    RollbackRequest,
    RollbackResponse,
    ToolCallSummary,
    WorkflowRunDetail,
    WorkflowRunSummary,
)

logger = logging.getLogger(__name__)


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""


class RollbackError(Exception):
    """Raised when a prompt rollback fails."""


class AuditService:
    """
    Application service for the Admin AI Audit Console.

    Dependencies are injected via constructor to support DI and testing.
    """

    def __init__(
        self,
        decision_repo: IAIDecisionRepository,
        feedback_repo: IFeedbackRepository,
        golden_dataset_service: GoldenDatasetService,
        prompt_label_service: Any,
        prompt_publication_repo: Any,
        evaluation_repo: Any,
        episodic_repo: Any,
        workflow_runner: Any,
        calibration_repo: Any,
        calibration_service: Any,
    ) -> None:
        self._decision_repo = decision_repo
        self._feedback_repo = feedback_repo
        self._golden_dataset = golden_dataset_service
        self._prompt_label_service = prompt_label_service
        self._prompt_pub_repo = prompt_publication_repo
        self._eval_repo = evaluation_repo
        self._episodic_repo = episodic_repo
        self._workflow_runner = workflow_runner
        self._calibration_repo = calibration_repo
        self._calibration_service = calibration_service

    # ── Decision log ──────────────────────────────────────────────────────────

    async def list_decisions(
        self, filters: DecisionLogFilter
    ) -> Tuple[List[AIDecisionRow], Optional[str]]:
        """List AI decisions with pagination and filtering."""
        return await self._decision_repo.list_paginated(filters)

    async def get_decision_detail(self, decision_id: UUID) -> AIDecisionDetail:
        """Return full decision detail; raises NotFoundError if absent."""
        decision = await self._decision_repo.get_by_id(decision_id)
        if decision is None:
            raise NotFoundError(f"ai_decision {decision_id} not found")
        return decision

    # ── Admin override ────────────────────────────────────────────────────────

    async def apply_override(
        self,
        request: AdminOverrideRequest,
        admin_user_id: UUID,
        admin_tenant_id: UUID,
    ) -> AdminOverrideResponse:
        """
        Apply an admin override to an AI decision.

        Steps:
        1. Validate decision exists.
        2. Write user_feedback row to Layer 4.
        3. Create golden dataset candidate (active=False).
        4. Generate rule-based proposed prompt adjustment.
        5. Return AdminOverrideResponse.
        """
        decision = await self._decision_repo.get_by_id(request.decision_id)
        if decision is None:
            raise NotFoundError(f"ai_decision {request.decision_id} not found")

        # Step 2: Write user_feedback row to Layer 4
        feedback = await self._feedback_repo.append_feedback(
            UserFeedbackCreate(
                tenant_id=admin_tenant_id,
                report_id=None,
                recommendation_id=None,
                feedback_type=FeedbackType.REJECT_WITH_FEEDBACK,
                feedback_text=request.override_reason,
                user_edit=request.corrected_output,
                reviewer_id=admin_user_id,
                source=FeedbackSource.HIL_ACTION,
            )
        )

        # Step 3: Create golden dataset candidate
        analogue_count = len(decision.retrieved_analogs) if decision.retrieved_analogs else 0
        candidate = await self._golden_dataset.create_candidate(
            GoldenDatasetItemCreate(
                input={
                    "inputs_full": decision.inputs_full,
                    "retrieved_analogs": decision.retrieved_analogs,
                },
                expected_output={"output_text": request.corrected_output},
                quality_metrics={},
                source="admin_override",
            )
        )

        # Step 4: Rule-based proposed prompt adjustment
        proposed_prompt_adjustment = (
            f"Agent {decision.agent_role} produced output that was manually corrected. "
            f"Original confidence: {decision.confidence:.2f}. "
            f"Suggested review: prompt may over-weight {analogue_count} analogues "
            f"when confidence is below {decision.confidence:.2f}."
        )

        logger.info(
            "AuditService.apply_override: decision=%s feedback=%s candidate=%s",
            request.decision_id,
            feedback.feedback_id,
            candidate.item_id,
        )

        return AdminOverrideResponse(
            decision_id=request.decision_id,
            feedback_id=feedback.feedback_id,
            golden_dataset_candidate_id=candidate.item_id,
            proposed_prompt_adjustment=proposed_prompt_adjustment,
            status="pending_review",
        )

    # ── Prompt version history ────────────────────────────────────────────────

    async def list_prompt_history(
        self, agent_role: str, limit: int = 50
    ) -> List[PromptVersionEntry]:
        """
        Return prompt publication history for an agent role.

        Enriches each entry with quality_metrics from the most recent
        evaluation_result matching the prompt SHA.
        """
        publications = await self._prompt_pub_repo.list_by_role(
            agent_role, limit=limit
        )

        # Collect all SHAs for bulk evaluation lookup
        entries: List[PromptVersionEntry] = []
        for pub in publications:
            # Look up quality metrics from evaluation results for this SHA
            quality_metrics = None
            try:
                eval_results = await self._eval_repo.list_recent_by_version(
                    prompt_version=pub.git_sha, limit=1
                )
                if eval_results:
                    latest = eval_results[0]
                    quality_metrics = latest.scores if hasattr(latest, "scores") else None
            except Exception:
                quality_metrics = None

            # Determine rolled_back_at: check if a rollback action exists for this SHA
            rolled_back_at = getattr(pub, "rolled_back_at", None)

            entries.append(
                PromptVersionEntry(
                    version_id=pub.git_sha,
                    agent_role=agent_role,
                    label_applied=pub.label,
                    published_at=pub.published_at,
                    rolled_back_at=rolled_back_at,
                    quality_metrics=quality_metrics,
                )
            )

        return entries

    async def rollback_prompt(self, request: RollbackRequest) -> RollbackResponse:
        """
        Roll back an agent's active prompt to a previous version.

        Calls IPromptLabelService.rollback(). Raises RollbackError on failure.
        """
        try:
            result = await self._prompt_label_service.rollback(
                request.agent_role, request.to_version
            )
        except Exception as exc:
            raise RollbackError(
                f"Prompt rollback failed for {request.agent_role} -> {request.to_version}: {exc}"
            ) from exc

        return RollbackResponse(
            agent_role=request.agent_role,
            previous_version=getattr(result, "previous_version", "unknown"),
            rolled_back_to=request.to_version,
            effective_at=getattr(result, "effective_at", datetime.now(timezone.utc)),
        )

    # ── Workflow history ──────────────────────────────────────────────────────

    async def list_workflow_runs(
        self,
        cursor: Optional[str],
        limit: int = 50,
    ) -> Tuple[List[WorkflowRunSummary], Optional[str]]:
        """Return paginated workflow run summaries."""
        runs, next_cursor = await self._episodic_repo.list_recent_runs(
            tenant_id=None, limit=limit, cursor=cursor
        )
        summaries = [
            WorkflowRunSummary(
                workflow_id=r.workflow_id,
                workflow_type=r.workflow_type,
                status=r.status,
                started_at=r.started_at,
                completed_at=r.completed_at,
                cost_usd=r.cost_usd,
                langfuse_trace_id=getattr(r, "langfuse_trace_id", None),
            )
            for r in runs
        ]
        return summaries, next_cursor

    async def get_workflow_detail(self, workflow_id: UUID) -> WorkflowRunDetail:
        """Return full workflow detail including invocations and tool calls."""
        run = await self._episodic_repo.get_workflow_run(workflow_id)
        if run is None:
            raise NotFoundError(f"workflow_run {workflow_id} not found")

        invocations_raw = await self._episodic_repo.list_invocations_for_run(
            workflow_id
        )
        tool_calls_raw = await self._episodic_repo.list_tool_calls_for_run(
            workflow_id
        )

        # Group tool calls by invocation_id
        tc_by_inv: dict[UUID, list] = {}
        for tc in tool_calls_raw:
            tc_by_inv.setdefault(tc.invocation_id, []).append(tc)

        agent_invocations = [
            AgentInvocationSummary(
                invocation_id=inv.invocation_id,
                agent_role_id=inv.agent_role_id,
                model_used=inv.model_used,
                prompt_version=inv.prompt_version,
                confidence=getattr(inv, "confidence", None),
                cost_usd=getattr(inv, "cost_usd", 0.0),
                duration_ms=getattr(inv, "duration_ms", 0),
                input_tokens=getattr(inv, "input_tokens", 0),
                output_tokens=getattr(inv, "output_tokens", 0),
                tool_calls=[
                    ToolCallSummary(
                        tool_call_id=tc.tool_call_id,
                        tool_name=tc.tool_name,
                        duration_ms=getattr(tc, "duration_ms", 0),
                        cost_tier=getattr(tc, "cost_tier", None),
                        cached=getattr(tc, "cached", False),
                    )
                    for tc in tc_by_inv.get(inv.invocation_id, [])
                ],
            )
            for inv in invocations_raw
        ]

        return WorkflowRunDetail(
            workflow_id=run.workflow_id,
            workflow_type=run.workflow_type,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            cost_usd=run.cost_usd,
            langfuse_trace_id=getattr(run, "langfuse_trace_id", None),
            agent_invocations=agent_invocations,
            final_state=getattr(run, "final_state", None),
        )

    async def rerun_workflow(
        self, request: RerunRequest, admin_user_id: UUID
    ) -> RerunResponse:
        """Re-run a workflow using its stored inputs and current production prompts."""
        run = await self._episodic_repo.get_workflow_run(request.workflow_id)
        if run is None:
            raise NotFoundError(f"workflow_run {request.workflow_id} not found")

        final_state = getattr(run, "final_state", None) or {}
        workflow_type = run.workflow_type
        inputs = final_state.get("inputs", {})

        new_workflow_id = await self._workflow_runner.dispatch(
            workflow_type=workflow_type, inputs=inputs
        )

        return RerunResponse(
            new_workflow_id=new_workflow_id,
            workflow_type=workflow_type,
            dispatched_at=datetime.now(timezone.utc),
        )

    # ── Calibration dashboard ─────────────────────────────────────────────────

    async def get_calibration_time_series(
        self, days: int, action_signal: Optional[str] = None
    ) -> list:
        """Return calibration result rows for the given lookback window."""
        return await self._calibration_repo.list_last_n_days(
            days=days, action_signal=action_signal
        )

    async def get_calibration_summary(self, days: int) -> Any:
        """Return aggregated calibration summary."""
        return await self._calibration_service.get_calibration_summary(days=days)
