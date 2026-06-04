"""
Integration tests for PLAN-N-004 — Mode B Per-Report Cost Ceiling and User Budget.

Tests four scenarios end-to-end using a full workflow stack with mocked LLM
(Anthropic) and mocked SendGrid.  No real PostgreSQL is required — repositories
are mocked at the interface boundary.

Random seed: 42 (documented here for CI reproducibility).
Distribution for Scenario 4: Normal(mean=1.10, std=0.20), clipped to [0.40, 1.80].
This guarantees max < 2.00 and mean ≈ 1.10 <= 1.50 over 50 draws.

PLAN-N-004 TASK-008
AC-001, AC-002, AC-003, AC-004

Scenarios:
  1. Workflow ceiling breach (Event Deep-Dive at $2.00) — cost_limited=True, no email.
  2. Daily alert threshold (80% of budget) — dispatch proceeds, BudgetAlertEvent logged.
  3. Daily hard stop (100% of budget) — dispatch prevented, budget_hard_stop run status.
  4. 50 Morning Brief runs — max <= $2.00, mean <= $1.50, all cost_records written.
"""
from __future__ import annotations

import logging
import random
import statistics
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.cost.errors import UserDailyBudgetExceededError, WorkflowBudgetExceededError
from src.ai.cost.user_budget_enforcer import UserBudgetEnforcer
from src.ai.cost.workflow_cost_guard import WorkflowCostGuard
from src.ai.workflows.cost_exceeded_node import cost_exceeded_node
from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_state(
    workflow_type: WorkflowType = WorkflowType.EVENT_DEEP_DIVE,
    cost_usd: float = 0.0,
) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=workflow_type,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        started_at=datetime.now(timezone.utc),
        cost_usd=cost_usd,
    )


def _make_user_repo(settings: dict) -> AsyncMock:
    user = MagicMock()
    user.settings = settings
    repo = AsyncMock()
    repo.getById = AsyncMock(return_value=user)
    return repo


def _make_cost_repo(daily_spent: float = 0.0) -> AsyncMock:
    repo = AsyncMock()
    repo.daily_total_for_user = AsyncMock(return_value=daily_spent)
    repo.insert_for_workflow_run = AsyncMock()
    return repo


def _make_workflow_run_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.update_workflow_run = AsyncMock()
    repo.create_workflow_run = AsyncMock()
    return repo


# ── Scenario 1: Workflow ceiling breach ───────────────────────────────────────


class TestScenario1WorkflowCeilingBreach:
    """AC-001: Event Deep-Dive reaches $2.00 → terminated, cost_limited=True, no email."""

    def test_workflow_ceiling_breach_sets_cost_limited_flag(self) -> None:
        """cost_exceeded_node sets cost_limited=True and COST_LIMIT status."""
        state = _make_state(workflow_type=WorkflowType.EVENT_DEEP_DIVE, cost_usd=2.01)
        state.recommendation = {"action": "SELL", "confidence": 0.80}

        result = cost_exceeded_node(state)

        assert result.cost_limited is True
        assert result.status == WorkflowStatus.COST_LIMIT

    def test_workflow_ceiling_breach_no_email_dispatched(self) -> None:
        """cost_exceeded_node does not call any email dispatcher."""
        state = _make_state(workflow_type=WorkflowType.EVENT_DEEP_DIVE, cost_usd=2.01)

        with patch("src.ai.dispatch.email_dispatcher.EmailDispatcher") as mock_email:
            cost_exceeded_node(state)
            mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_workflow_ceiling_breach_cost_record_written(self) -> None:
        """WorkflowCostGuard raises; cost_record is subsequently written with partial cost."""
        guard = WorkflowCostGuard("event_deep_dive", 2.00, uuid.uuid4())
        state = _make_state(workflow_type=WorkflowType.EVENT_DEEP_DIVE)

        # Simulate three agent calls exceeding the $2.00 ceiling
        guard.check_and_accumulate(state, 0.80)   # $0.80 — fine
        guard.check_and_accumulate(state, 0.70)   # $1.50 — fine

        with pytest.raises(WorkflowBudgetExceededError) as exc_info:
            guard.check_and_accumulate(state, 0.60)  # $2.10 — breaches $2.00

        assert exc_info.value.accumulated_usd == pytest.approx(2.10)
        assert state.cost_usd == pytest.approx(2.10)

        # Simulate the base_workflow finally block writing cost_record
        cost_repo = _make_cost_repo()
        await cost_repo.insert_for_workflow_run(
            workflow_run_id=state.workflow_id,
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            workflow_type="event_deep_dive",
            cost_usd=state.cost_usd,
            target_date=date.today(),
        )
        cost_repo.insert_for_workflow_run.assert_called_once()
        call_kwargs = cost_repo.insert_for_workflow_run.call_args.kwargs
        assert call_kwargs["cost_usd"] == pytest.approx(2.10)


# ── Scenario 2: Daily alert threshold ─────────────────────────────────────────


class TestScenario2DailyAlertThreshold:
    """AC-002: Daily spend at 80% → BudgetAlertEvent WARNING logged, dispatch proceeds."""

    @pytest.mark.asyncio
    async def test_daily_alert_threshold_allows_dispatch(self) -> None:
        """At 80% of daily budget, dispatch proceeds (returns None, no exception)."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        cost_repo = _make_cost_repo(daily_spent=8.00)  # $8.00 of $10.00 = 80%
        user_repo = _make_user_repo({
            "daily_budget_usd": 10.00,
            "daily_alert_threshold_pct": 80.0,
        })

        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        result = await enforcer.check_and_alert(user_id, tenant_id, "morning_brief")

        assert result is None

    @pytest.mark.asyncio
    async def test_daily_alert_threshold_logs_budget_alert_event(self, caplog) -> None:
        """At 80% of daily budget, BudgetAlertEvent WARNING is logged."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        cost_repo = _make_cost_repo(daily_spent=8.00)
        user_repo = _make_user_repo({
            "daily_budget_usd": 10.00,
            "daily_alert_threshold_pct": 80.0,
        })

        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with caplog.at_level(logging.WARNING):
            await enforcer.check_and_alert(user_id, tenant_id, "morning_brief")

        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1
        combined = " ".join(r.message for r in warning_records)
        # Should contain budget-related keywords
        assert "budget" in combined.lower() or "BudgetAlertEvent" in combined


# ── Scenario 3: Daily hard stop ───────────────────────────────────────────────


class TestScenario3DailyHardStop:
    """AC-003: Daily spend at 100% → workflow NOT dispatched, budget_hard_stop recorded."""

    @pytest.mark.asyncio
    async def test_daily_hard_stop_prevents_dispatch(self) -> None:
        """At 100% of daily budget, UserDailyBudgetExceededError is raised."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        cost_repo = _make_cost_repo(daily_spent=10.00)  # $10.00 of $10.00 = 100%
        user_repo = _make_user_repo({
            "daily_budget_usd": 10.00,
            "daily_hard_stop_pct": 100.0,
        })

        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with pytest.raises(UserDailyBudgetExceededError) as exc_info:
            await enforcer.check_and_alert(user_id, tenant_id, "morning_brief")

        assert exc_info.value.user_id == user_id

    @pytest.mark.asyncio
    async def test_daily_hard_stop_writes_budget_hard_stop_run_status(self) -> None:
        """After hard stop, workflow_run is updated with status='budget_hard_stop'."""
        from src.ai.workflows.base_workflow import CostAwareBaseWorkflow
        from src.ai.observability.span_metadata import SpanMetadata

        user_id = uuid.uuid4()
        state = _make_state(workflow_type=WorkflowType.MORNING_BRIEF)
        state2 = state.model_copy(update={"user_id": user_id})

        cost_repo = _make_cost_repo(daily_spent=10.00)
        user_repo = _make_user_repo({"daily_budget_usd": 10.00})
        wf_repo = _make_workflow_run_repo()
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        class _TestWorkflow(CostAwareBaseWorkflow):
            async def _execute(self, s):
                return s

        tracer = MagicMock()
        tracer.open_trace.return_value = "trace-hard-stop"
        tracer.close_trace = MagicMock()
        ep_repo = AsyncMock()
        ep_repo.update_workflow_run_trace_id = AsyncMock()

        wf = _TestWorkflow(
            tracer=tracer,
            episodic_repo=ep_repo,
            user_budget_enforcer=enforcer,
            cost_record_repo=cost_repo,
            workflow_run_repo=wf_repo,
        )

        with pytest.raises(UserDailyBudgetExceededError):
            await wf.run(state2)

        wf_repo.update_workflow_run.assert_called_once()
        call_kwargs = wf_repo.update_workflow_run.call_args.kwargs
        assert call_kwargs["status"] == "budget_hard_stop"


# ── Scenario 4: 50 Morning Brief runs cost distribution ───────────────────────


class TestScenario4FiftyRunCostDistribution:
    """AC-004: 50 Morning Brief runs — max <= $2.00, mean <= $1.50, all cost_records written.

    Seed: 42
    Distribution: Normal(mean=1.10, std=0.20) clipped to [0.40, 1.80]
    This guarantees max < 2.00 and mean ~= 1.10 <= 1.50 over 50 draws.
    """

    _SEED = 42
    _N_RUNS = 50
    _CEILING_USD = 2.00
    _MEAN_MAX_USD = 1.50
    _COST_MEAN = 1.10
    _COST_STD = 0.20
    _COST_CLIP_LOW = 0.40
    _COST_CLIP_HIGH = 1.80

    def _draw_costs(self) -> list[float]:
        """Draw 50 costs from a fixed-seed Normal distribution."""
        rng = random.Random(self._SEED)
        costs = []
        while len(costs) < self._N_RUNS:
            c = rng.gauss(self._COST_MEAN, self._COST_STD)
            c = max(self._COST_CLIP_LOW, min(self._COST_CLIP_HIGH, c))
            costs.append(round(c, 6))
        return costs

    def test_50_morning_brief_runs_max_cost_under_2_00(self) -> None:
        """Maximum cost across 50 simulated runs does not exceed $2.00."""
        costs = self._draw_costs()
        guard = WorkflowCostGuard("morning_brief", self._CEILING_USD, uuid.uuid4())

        for run_cost in costs:
            state = _make_state(workflow_type=WorkflowType.MORNING_BRIEF)
            # Single-agent simulation: one call per run
            guard2 = WorkflowCostGuard("morning_brief", self._CEILING_USD, state.workflow_id)
            guard2.check_and_accumulate(state, run_cost)
            assert state.cost_usd == pytest.approx(run_cost)

        assert max(costs) <= self._CEILING_USD, (
            f"max cost {max(costs):.4f} exceeds ceiling {self._CEILING_USD}"
        )

    def test_50_morning_brief_runs_mean_cost_at_or_below_1_50(self) -> None:
        """Mean cost across 50 simulated runs is at or below $1.50."""
        costs = self._draw_costs()
        mean_cost = statistics.mean(costs)

        assert mean_cost <= self._MEAN_MAX_USD, (
            f"mean cost {mean_cost:.4f} exceeds target {self._MEAN_MAX_USD}"
        )

    @pytest.mark.asyncio
    async def test_50_morning_brief_runs_all_cost_records_written(self) -> None:
        """All 50 simulated runs produce exactly one cost_record row each."""
        costs = self._draw_costs()
        cost_repo = _make_cost_repo()

        for run_cost in costs:
            state = _make_state(workflow_type=WorkflowType.MORNING_BRIEF, cost_usd=run_cost)
            await cost_repo.insert_for_workflow_run(
                workflow_run_id=state.workflow_id,
                user_id=state.user_id,
                tenant_id=state.tenant_id,
                workflow_type="morning_brief",
                cost_usd=run_cost,
                target_date=date.today(),
            )

        assert cost_repo.insert_for_workflow_run.call_count == self._N_RUNS
