"""
BaseWorkflow — lifecycle management for LangGraph-based workflow runs.

Architecture §7.1: Langfuse trace opened at workflow entry, closed at exit.
The langfuse_trace_id is stored on the workflow_run row via the episodic
repository (cross-link between PostgreSQL and Langfuse, Architecture §10).

Subclasses must implement _execute(state) with the actual node graph.

PLAN-F-030 TASK-011: BudgetGuard.assert_under_limit() is called at workflow
entry to enforce the monthly AI spend cap (Architecture §12.6).

PLAN-N-004: CostAwareBaseWorkflow extends BaseWorkflow with per-user daily
budget enforcement (UserBudgetEnforcer) and cost_record telemetry writes.
The three-tier cost hierarchy is:
  Tier 1: per-agent ExecutionLimiter (PLAN-F-011)
  Tier 2: per-workflow WorkflowCostGuard
  Tier 3: per-user daily UserBudgetEnforcer (this class)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any

from src.ai.observability.span_metadata import SpanMetadata
from src.ai.observability.tracer import ILangfuseTracer
from src.ai.cost.errors import UserDailyBudgetExceededError, WorkflowBudgetExceededError

logger = logging.getLogger(__name__)


class WorkflowState:
    """Minimal mutable workflow state passed through all nodes.

    Subclasses add domain-specific fields (event data, scores, etc.).
    """

    def __init__(
        self,
        workflow_id: Any,
        workflow_type: str,
        tenant_id: Any,
        user_id: Any,
    ) -> None:
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.trace_id: str | None = None
        self.cost_usd: float = 0.0


class BaseWorkflow(ABC):
    """Abstract base for all StokAI workflows.

    Parameters
    ----------
    tracer:
        ILangfuseTracer implementation.
    episodic_repo:
        Repository with update_workflow_run_trace_id; persists langfuse_trace_id.
    """

    def __init__(
        self,
        tracer: ILangfuseTracer,
        episodic_repo: Any,
        budget_guard: Any = None,
    ) -> None:
        self._tracer = tracer
        self._episodic_repo = episodic_repo
        self._budget_guard = budget_guard

    async def run(self, state: Any) -> Any:
        """Run the full workflow: open trace → execute → close trace.

        Opens a Langfuse trace, stores trace_id on state, delegates to
        _execute(), closes the trace and persists langfuse_trace_id to the
        workflow_run row.
        """
        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            agent_role_id=None,
            prompt_version=None,
            model_used=None,
            confidence=None,
            cost_usd=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=None,
            tools_called=None,
            state_snapshot_ref=None,
        )

        # PLAN-F-030: Enforce budget cap before any AI API calls (Architecture §12.6)
        if self._budget_guard is not None:
            await self._budget_guard.assert_under_limit(state.tenant_id)

        trace_id = self._tracer.open_trace(root_metadata)
        state.trace_id = trace_id
        logger.debug("Workflow %s started, trace_id=%s", state.workflow_id, trace_id)

        try:
            state = await self._execute(state)
        finally:
            self._tracer.close_trace(trace_id, cost_usd=getattr(state, "cost_usd", 0.0))
            logger.debug("Workflow %s finished, trace_id=%s", state.workflow_id, trace_id)

            # Authoritative cross-link: persist trace_id to PostgreSQL
            await self._episodic_repo.update_workflow_run_trace_id(
                workflow_run_id=state.workflow_id,
                trace_id=trace_id,
            )

        return state

    @abstractmethod
    async def _execute(self, state: Any) -> Any:
        """Implement the actual node graph execution."""


class CostAwareBaseWorkflow(BaseWorkflow):
    """BaseWorkflow extended with per-user daily budget enforcement and cost telemetry.

    PLAN-N-004 Tier 3 integration point (ARCHITECTURE §12.6).

    Additional lifecycle steps:
      1. Pre-dispatch: UserBudgetEnforcer.check_and_alert() before _execute().
         - UserDailyBudgetExceededError → write "budget_hard_stop" run, re-raise.
      2. Post-run (finally): insert cost_record row with final cost_usd.
      3. On WorkflowBudgetExceededError: set workflow_run.cost_limited=True,
         status="cost_exceeded", re-raise.

    Parameters
    ----------
    user_budget_enforcer:
        UserBudgetEnforcer instance (PLAN-N-004).
    cost_record_repo:
        ICostRecordRepository with insert_for_workflow_run().
    workflow_run_repo:
        WorkflowRunRepository with update_workflow_run() and create_workflow_run().
    """

    def __init__(
        self,
        tracer: ILangfuseTracer,
        episodic_repo: Any,
        user_budget_enforcer: Any,
        cost_record_repo: Any,
        workflow_run_repo: Any,
        budget_guard: Any = None,
    ) -> None:
        super().__init__(tracer=tracer, episodic_repo=episodic_repo, budget_guard=budget_guard)
        self._user_budget_enforcer = user_budget_enforcer
        self._cost_record_repo = cost_record_repo
        self._workflow_run_repo = workflow_run_repo

    async def run(self, state: Any) -> Any:
        """Run workflow with budget enforcement and cost telemetry.

        Lifecycle:
          1. Call UserBudgetEnforcer.check_and_alert() — may raise UserDailyBudgetExceededError.
          2. Open Langfuse trace.
          3. Run _execute() (the LangGraph graph).
          4. In finally: insert cost_record row.
          5. On WorkflowBudgetExceededError: update workflow_run with cost_limited=True.
          6. On UserDailyBudgetExceededError (pre-dispatch): update workflow_run with
             status="budget_hard_stop", re-raise without running graph.
        """
        workflow_type_str = (
            state.workflow_type.value
            if hasattr(state.workflow_type, "value")
            else str(state.workflow_type)
        )

        # ── Tier 3: per-user daily budget check (ARCHITECTURE §12.6) ─────────
        try:
            await self._user_budget_enforcer.check_and_alert(
                user_id=state.user_id,
                tenant_id=state.tenant_id,
                workflow_type=workflow_type_str,
            )
        except UserDailyBudgetExceededError:
            # Write a stub workflow_run row to record the hard stop.
            await self._workflow_run_repo.update_workflow_run(
                workflow_id=state.workflow_id,
                status="budget_hard_stop",
                cost_usd=0.0,
                cost_limited=False,
                completed_at=datetime.now(tz=timezone.utc),
            )
            raise

        # ── Open Langfuse trace (inherited from BaseWorkflow pattern) ─────────
        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            agent_role_id=None,
            prompt_version=None,
            model_used=None,
            confidence=None,
            cost_usd=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=None,
            tools_called=None,
            state_snapshot_ref=None,
        )
        trace_id = self._tracer.open_trace(root_metadata)
        # Store trace_id on state — use langfuse_trace_id if available (Pydantic model)
        # Fall back to trace_id attribute for simple mutable state objects
        try:
            state.langfuse_trace_id = trace_id  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
        try:
            state.trace_id = trace_id  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
        logger.debug(
            "CostAwareBaseWorkflow %s started, trace_id=%s", state.workflow_id, trace_id
        )

        cost_exceeded = False
        try:
            state = await self._execute(state)
        except WorkflowBudgetExceededError:
            cost_exceeded = True
            raise
        finally:
            self._tracer.close_trace(trace_id, cost_usd=getattr(state, "cost_usd", 0.0))
            logger.debug(
                "CostAwareBaseWorkflow %s finished, trace_id=%s",
                state.workflow_id,
                trace_id,
            )

            # Persist trace_id cross-link
            await self._episodic_repo.update_workflow_run_trace_id(
                workflow_run_id=state.workflow_id,
                trace_id=trace_id,
            )

            # ── Post-run cost_record insert (fires on any outcome) ────────────
            try:
                await self._cost_record_repo.insert_for_workflow_run(
                    workflow_run_id=state.workflow_id,
                    user_id=state.user_id,
                    tenant_id=state.tenant_id,
                    workflow_type=workflow_type_str,
                    cost_usd=getattr(state, "cost_usd", 0.0),
                    target_date=date.today(),
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "CostAwareBaseWorkflow: failed to insert cost_record for "
                    "workflow_id=%s — cost telemetry may be incomplete",
                    state.workflow_id,
                )

            # ── Update workflow_run status ────────────────────────────────────
            if cost_exceeded:
                await self._workflow_run_repo.update_workflow_run(
                    workflow_id=state.workflow_id,
                    status="cost_exceeded",
                    cost_limited=True,
                    cost_usd=getattr(state, "cost_usd", 0.0),
                    completed_at=datetime.now(tz=timezone.utc),
                )
            else:
                await self._workflow_run_repo.update_workflow_run(
                    workflow_id=state.workflow_id,
                    status=getattr(getattr(state, "status", None), "value", "COMPLETED"),
                    cost_limited=False,
                    cost_usd=getattr(state, "cost_usd", 0.0),
                    completed_at=datetime.now(tz=timezone.utc),
                )

        return state
