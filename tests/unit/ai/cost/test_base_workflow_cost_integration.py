"""
Unit tests for base_workflow.py cost governance integration (PLAN-N-004 TASK-005).

Tests verify:
  1. UserBudgetEnforcer.check_and_alert called before graph.ainvoke.
  2. Hard stop prevents graph invocation and writes "budget_hard_stop" run.
  3. cost_record written on successful run, cost_exceeded error, any exception.
  4. cost_limited flag set correctly on WorkflowBudgetExceededError.

All external dependencies are mocked.  No LangGraph or DB required.

TDD: tests were written before the implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from src.ai.cost.errors import UserDailyBudgetExceededError, WorkflowBudgetExceededError
from src.ai.workflows.base_workflow import CostAwareBaseWorkflow
from src.ai.workflows.state import WorkflowState, WorkflowType


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_state(cost_usd: float = 0.0) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid4(),
        workflow_type=WorkflowType.MORNING_BRIEF,
        tenant_id=uuid4(),
        user_id=uuid4(),
        started_at=datetime.now(timezone.utc),
        cost_usd=cost_usd,
    )


def _make_workflow(
    enforcer: object,
    cost_repo: object,
    workflow_run_repo: object,
    graph_result: WorkflowState | None = None,
    graph_side_effect=None,
) -> "CostAwareBaseWorkflow":
    """Construct a CostAwareBaseWorkflow with mocked dependencies."""

    class _TestWorkflow(CostAwareBaseWorkflow):
        async def _execute(self, state):
            if graph_side_effect is not None:
                raise graph_side_effect
            return graph_result if graph_result is not None else state

    tracer = MagicMock()
    tracer.open_trace.return_value = "trace-123"
    tracer.close_trace = MagicMock()

    episodic_repo = AsyncMock()
    episodic_repo.update_workflow_run_trace_id = AsyncMock()

    return _TestWorkflow(
        tracer=tracer,
        episodic_repo=episodic_repo,
        user_budget_enforcer=enforcer,
        cost_record_repo=cost_repo,
        workflow_run_repo=workflow_run_repo,
    )


def _make_enforcer(side_effect=None) -> AsyncMock:
    enforcer = AsyncMock()
    enforcer.check_and_alert = AsyncMock(side_effect=side_effect)
    return enforcer


def _make_cost_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.insert_for_workflow_run = AsyncMock()
    return repo


def _make_workflow_run_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_workflow_run = AsyncMock()
    repo.update_workflow_run = AsyncMock()
    return repo


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCostAwareBaseWorkflow:

    async def test_budget_enforcer_called_before_graph_invoke(self) -> None:
        """check_and_alert is called before _execute()."""
        call_order = []

        enforcer = AsyncMock()
        async def _check(*_args, **_kwargs):
            call_order.append("enforcer")
        enforcer.check_and_alert = AsyncMock(side_effect=_check)

        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        class _TrackedWorkflow(CostAwareBaseWorkflow):
            async def _execute(self, state):
                call_order.append("execute")
                return state

        tracer = MagicMock()
        tracer.open_trace.return_value = "t"
        tracer.close_trace = MagicMock()
        ep_repo = AsyncMock()
        ep_repo.update_workflow_run_trace_id = AsyncMock()

        wf = _TrackedWorkflow(
            tracer=tracer,
            episodic_repo=ep_repo,
            user_budget_enforcer=enforcer,
            cost_record_repo=cost_repo,
            workflow_run_repo=wf_repo,
        )

        state = _make_state()
        await wf.run(state)

        assert call_order.index("enforcer") < call_order.index("execute")

    async def test_hard_stop_prevents_graph_invoke(self) -> None:
        """When enforcer raises UserDailyBudgetExceededError, _execute is never called."""
        execute_called = []
        enforcer = _make_enforcer(
            side_effect=UserDailyBudgetExceededError(
                user_id=uuid4(), daily_budget_usd=10.0, spent_today_usd=10.0
            )
        )
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        class _TrackedWorkflow(CostAwareBaseWorkflow):
            async def _execute(self, state):
                execute_called.append(True)
                return state

        tracer = MagicMock()
        tracer.open_trace.return_value = "t"
        tracer.close_trace = MagicMock()
        ep_repo = AsyncMock()
        ep_repo.update_workflow_run_trace_id = AsyncMock()

        wf = _TrackedWorkflow(
            tracer=tracer,
            episodic_repo=ep_repo,
            user_budget_enforcer=enforcer,
            cost_record_repo=cost_repo,
            workflow_run_repo=wf_repo,
        )

        state = _make_state()
        with pytest.raises(UserDailyBudgetExceededError):
            await wf.run(state)

        assert execute_called == []

    async def test_hard_stop_writes_workflow_run_with_budget_hard_stop_status(self) -> None:
        """After UserDailyBudgetExceededError, workflow_run.status = 'budget_hard_stop'."""
        enforcer = _make_enforcer(
            side_effect=UserDailyBudgetExceededError(
                user_id=uuid4(), daily_budget_usd=10.0, spent_today_usd=10.0
            )
        )
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()
        wf = _make_workflow(enforcer, cost_repo, wf_repo)

        state = _make_state()
        with pytest.raises(UserDailyBudgetExceededError):
            await wf.run(state)

        wf_repo.update_workflow_run.assert_called_once()
        call_kwargs = wf_repo.update_workflow_run.call_args
        assert call_kwargs is not None
        # status should be "budget_hard_stop"
        status_arg = (
            call_kwargs.kwargs.get("status")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        )
        assert status_arg == "budget_hard_stop"

    async def test_cost_record_written_on_successful_run(self) -> None:
        """After normal completion with cost_usd=1.20, insert_for_workflow_run called."""
        enforcer = _make_enforcer()
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        final_state = _make_state(cost_usd=1.20)
        wf = _make_workflow(enforcer, cost_repo, wf_repo, graph_result=final_state)

        await wf.run(final_state)

        cost_repo.insert_for_workflow_run.assert_called_once()
        call_kwargs = cost_repo.insert_for_workflow_run.call_args.kwargs
        assert call_kwargs["cost_usd"] == pytest.approx(1.20)

    async def test_cost_record_written_on_cost_exceeded_error(self) -> None:
        """WorkflowBudgetExceededError: insert_for_workflow_run called with partial cost."""
        enforcer = _make_enforcer()
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        state = _make_state(cost_usd=0.0)
        workflow_id = state.workflow_id
        exc = WorkflowBudgetExceededError(
            workflow_type="morning_brief",
            ceiling_usd=2.00,
            accumulated_usd=2.01,
            workflow_id=workflow_id,
        )
        # Simulate state mutated to 2.01 before exception
        state.cost_usd = 2.01

        wf = _make_workflow(enforcer, cost_repo, wf_repo, graph_side_effect=exc)

        with pytest.raises(WorkflowBudgetExceededError):
            await wf.run(state)

        cost_repo.insert_for_workflow_run.assert_called_once()

    async def test_cost_record_written_on_unexpected_exception(self) -> None:
        """Generic RuntimeError: insert_for_workflow_run still called (finally block)."""
        enforcer = _make_enforcer()
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()
        wf = _make_workflow(enforcer, cost_repo, wf_repo, graph_side_effect=RuntimeError("boom"))

        state = _make_state()
        with pytest.raises(RuntimeError):
            await wf.run(state)

        cost_repo.insert_for_workflow_run.assert_called_once()

    async def test_cost_limited_flag_set_on_budget_exceeded(self) -> None:
        """WorkflowBudgetExceededError: workflow_run updated with cost_limited=True."""
        enforcer = _make_enforcer()
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        state = _make_state()
        exc = WorkflowBudgetExceededError(
            workflow_type="morning_brief",
            ceiling_usd=2.00,
            accumulated_usd=2.01,
            workflow_id=state.workflow_id,
        )
        wf = _make_workflow(enforcer, cost_repo, wf_repo, graph_side_effect=exc)

        with pytest.raises(WorkflowBudgetExceededError):
            await wf.run(state)

        wf_repo.update_workflow_run.assert_called_once()
        call_kwargs = wf_repo.update_workflow_run.call_args.kwargs
        assert call_kwargs.get("cost_limited") is True
        assert call_kwargs.get("status") == "cost_exceeded"

    async def test_cost_limited_false_on_normal_completion(self) -> None:
        """Normal completion: workflow_run updated with cost_limited=False."""
        enforcer = _make_enforcer()
        cost_repo = _make_cost_repo()
        wf_repo = _make_workflow_run_repo()

        state = _make_state(cost_usd=0.80)
        wf = _make_workflow(enforcer, cost_repo, wf_repo, graph_result=state)

        await wf.run(state)

        wf_repo.update_workflow_run.assert_called_once()
        call_kwargs = wf_repo.update_workflow_run.call_args.kwargs
        assert call_kwargs.get("cost_limited") is False
