"""ExecutionLimiter — enforces per-agent execution limits.

Stateless: callers track state (token counts, iteration number, etc.).
Each check method raises LimitExceededError when actual >= limit.

REQ-N-003: per-agent cost_ceiling_usd enforced here.
"""
from __future__ import annotations

from src.ai.limits.errors import LimitExceededError, LimitType
from src.ai.registry.agent_definition import AgentLimits


class ExecutionLimiter:
    """Enforces the four execution limits defined in an agent's AgentLimits.

    Designed to be stateless: the caller (e.g. a LangGraph node) tracks
    running totals and calls the relevant check method before each operation.
    check_elapsed is designed for use with asyncio.wait_for wrappers.

    Args:
        limits: The AgentLimits parsed from the agent's YAML definition.
        agent_role_id: The agent's role_id, attached to every error for routing.
    """

    def __init__(self, limits: AgentLimits, agent_role_id: str) -> None:
        self._limits = limits
        self._agent_role_id = agent_role_id

    def check_input_tokens(self, count: int) -> None:
        """Raise LimitExceededError if count >= max_input_tokens.

        Args:
            count: Number of input tokens in the current request.
        """
        if count >= self._limits.max_input_tokens:
            raise LimitExceededError(
                limit_type=LimitType.MAX_INPUT_TOKENS,
                limit_value=float(self._limits.max_input_tokens),
                actual_value=float(count),
                agent_role_id=self._agent_role_id,
            )

    def check_iteration(self, current: int) -> None:
        """Raise LimitExceededError if current >= max_iterations.

        Args:
            current: The current iteration number (0-indexed or 1-indexed, caller decides).
        """
        if current >= self._limits.max_iterations:
            raise LimitExceededError(
                limit_type=LimitType.MAX_ITERATIONS,
                limit_value=float(self._limits.max_iterations),
                actual_value=float(current),
                agent_role_id=self._agent_role_id,
            )

    def check_elapsed(self, elapsed_seconds: float) -> None:
        """Raise LimitExceededError if elapsed_seconds >= timeout_seconds.

        Designed for use as a predicate with asyncio.wait_for().

        Args:
            elapsed_seconds: Wall-clock time elapsed since the agent node started.
        """
        if elapsed_seconds >= self._limits.timeout_seconds:
            raise LimitExceededError(
                limit_type=LimitType.TIMEOUT,
                limit_value=float(self._limits.timeout_seconds),
                actual_value=elapsed_seconds,
                agent_role_id=self._agent_role_id,
            )

    def check_cost(self, accumulated_usd: float) -> None:
        """Raise LimitExceededError if accumulated_usd >= cost_ceiling_usd.

        REQ-N-003: per-agent cost ceiling enforced here.

        Args:
            accumulated_usd: Total USD spent by this agent in the current invocation.
        """
        if accumulated_usd >= self._limits.cost_ceiling_usd:
            raise LimitExceededError(
                limit_type=LimitType.COST_CEILING,
                limit_value=self._limits.cost_ceiling_usd,
                actual_value=accumulated_usd,
                agent_role_id=self._agent_role_id,
            )
