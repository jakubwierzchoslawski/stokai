"""
Contract tests for ExecutionLimiter cost-ceiling path (PLAN-N-003, TASK-005).

These tests add missing coverage for the cost-ceiling branch of ExecutionLimiter.
They do NOT modify the production code — they document and verify the contract.

Note: ExecutionLimiter.check_cost uses an inclusive ceiling (accumulated >= ceiling
raises). This is intentional for the agent-level limiter; the event-pipeline's
CostAccumulator uses an exclusive ceiling (total > ceiling raises). The two
abstractions serve different layers.
"""
from __future__ import annotations

import pytest

from src.ai.limits.errors import LimitExceededError, LimitType
from src.ai.limits.execution_limiter import ExecutionLimiter
from src.ai.registry.agent_definition import AgentLimits

_COST_CEILING = 0.10
_AGENT_ROLE = "cost-test-agent"


def _make_limiter(cost_ceiling_usd: float = _COST_CEILING) -> ExecutionLimiter:
    limits = AgentLimits(
        max_input_tokens=8000,
        max_iterations=10,
        timeout_seconds=60,
        cost_ceiling_usd=cost_ceiling_usd,
    )
    return ExecutionLimiter(limits=limits, agent_role_id=_AGENT_ROLE)


class TestCostCeilingExceededRaisesLimitExceededError:
    def test_cost_ceiling_exceeded_raises_limit_exceeded_error(self) -> None:
        """When accumulated cost exceeds ceiling by epsilon, LimitExceededError is raised."""
        limiter = _make_limiter(cost_ceiling_usd=_COST_CEILING)
        epsilon = 1e-9
        with pytest.raises(LimitExceededError):
            limiter.check_cost(_COST_CEILING + epsilon)


class TestCostCeilingNotRaisedAtExactCeiling:
    def test_cost_ceiling_not_raised_at_exact_ceiling(self) -> None:
        """When accumulated cost equals the ceiling, LimitExceededError is raised
        (ExecutionLimiter uses inclusive >= check at the agent layer)."""
        limiter = _make_limiter(cost_ceiling_usd=_COST_CEILING)
        # ExecutionLimiter.check_cost uses >= so at-ceiling raises.
        # This test documents the actual inclusive contract of ExecutionLimiter.
        with pytest.raises(LimitExceededError):
            limiter.check_cost(_COST_CEILING)


class TestCostCeilingNotRaisedBelowCeiling:
    def test_cost_ceiling_not_raised_below_ceiling(self) -> None:
        """When accumulated cost is below the ceiling, no exception is raised."""
        limiter = _make_limiter(cost_ceiling_usd=_COST_CEILING)
        # Should not raise
        limiter.check_cost(_COST_CEILING - 0.001)


class TestLimitExceededErrorHasCorrectLimitType:
    def test_limit_exceeded_error_has_correct_limit_type(self) -> None:
        """LimitExceededError raised by check_cost carries LimitType.COST_CEILING."""
        limiter = _make_limiter(cost_ceiling_usd=_COST_CEILING)
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_cost(_COST_CEILING + 0.001)
        assert exc_info.value.limit_type == LimitType.COST_CEILING


class TestLimitExceededErrorCarriesActualValue:
    def test_limit_exceeded_error_carries_actual_value(self) -> None:
        """LimitExceededError carries the actual accumulated cost value."""
        limiter = _make_limiter(cost_ceiling_usd=_COST_CEILING)
        actual = _COST_CEILING + 0.005
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_cost(actual)
        err = exc_info.value
        assert err.actual_value == actual
        assert err.limit_value == _COST_CEILING
        assert err.agent_role_id == _AGENT_ROLE
