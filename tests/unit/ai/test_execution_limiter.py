"""Unit tests for ExecutionLimiter.

TDD: tests written before implementation.
"""
from __future__ import annotations

import json

import pytest

from src.ai.limits.errors import LimitExceededError, LimitType
from src.ai.registry.agent_definition import AgentLimits


def _make_limits(**overrides) -> AgentLimits:
    defaults = {
        "max_input_tokens": 8000,
        "max_iterations": 3,
        "timeout_seconds": 60,
        "cost_ceiling_usd": 0.10,
    }
    defaults.update(overrides)
    return AgentLimits(**defaults)


class TestCheckInputTokensUnderLimitPasses:
    def test_check_input_tokens_under_limit_passes(self) -> None:
        """Token count below ceiling does not raise."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(max_input_tokens=8000),
            agent_role_id="relevance-analyst",
        )
        # Should not raise
        limiter.check_input_tokens(7999)


class TestCheckInputTokensAtLimitRaisesLimitExceededError:
    def test_check_input_tokens_at_limit_raises_limit_exceeded_error(self) -> None:
        """Token count equal to ceiling raises LimitExceededError."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(max_input_tokens=8000),
            agent_role_id="relevance-analyst",
        )
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_input_tokens(8000)

        err = exc_info.value
        assert err.limit_type == LimitType.MAX_INPUT_TOKENS
        assert err.limit_value == 8000
        assert err.actual_value == 8000
        assert err.agent_role_id == "relevance-analyst"


class TestCheckIterationOverLimitRaises:
    def test_check_iteration_over_limit_raises(self) -> None:
        """Iteration count >= max_iterations raises LimitExceededError."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(max_iterations=3),
            agent_role_id="anomaly-detector",
        )
        # iteration 3 == max_iterations → should raise
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_iteration(3)

        assert exc_info.value.limit_type == LimitType.MAX_ITERATIONS
        assert exc_info.value.agent_role_id == "anomaly-detector"


class TestCheckElapsedOverTimeoutRaises:
    def test_check_elapsed_over_timeout_raises(self) -> None:
        """Elapsed time >= timeout_seconds raises LimitExceededError."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(timeout_seconds=60),
            agent_role_id="exposure-analyst",
        )
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_elapsed(60.0)

        assert exc_info.value.limit_type == LimitType.TIMEOUT


class TestCheckCostAtCeilingRaises:
    def test_check_cost_at_ceiling_raises(self) -> None:
        """Accumulated cost >= cost_ceiling_usd raises LimitExceededError."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(cost_ceiling_usd=0.10),
            agent_role_id="historical-context-agent",
        )
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_cost(0.10)

        assert exc_info.value.limit_type == LimitType.COST_CEILING


class TestLimitExceededErrorIsJsonSerializable:
    def test_limit_exceeded_error_is_json_serializable(self) -> None:
        """json.dumps(err.to_dict()) must not raise."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(max_input_tokens=100),
            agent_role_id="qa-analyst",
        )
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_input_tokens(100)

        serialised = json.dumps(exc_info.value.to_dict())
        assert isinstance(serialised, str)


class TestLimitExceededErrorIncludesAgentRoleId:
    def test_limit_exceeded_error_includes_agent_role_id(self) -> None:
        """The error carries agent_role_id for downstream HIL routing."""
        from src.ai.limits.execution_limiter import ExecutionLimiter

        limiter = ExecutionLimiter(
            limits=_make_limits(max_iterations=1),
            agent_role_id="narrative-writer",
        )
        with pytest.raises(LimitExceededError) as exc_info:
            limiter.check_iteration(1)

        assert exc_info.value.agent_role_id == "narrative-writer"
