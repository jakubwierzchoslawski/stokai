"""LimitExceededError and LimitType — structured errors for execution limit violations.

REQ-N-003: per-agent cost_ceiling_usd enforced at runtime.
"""
from __future__ import annotations

from enum import Enum


class LimitType(str, Enum):
    """Identifies which execution limit was exceeded."""

    MAX_INPUT_TOKENS = "max_input_tokens"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout_seconds"
    COST_CEILING = "cost_ceiling_usd"


class LimitExceededError(Exception):
    """Raised when an agent node exceeds a configured execution limit.

    Carry structured context so callers can route to HIL without
    parsing the message string.

    Args:
        limit_type: Which limit was breached.
        limit_value: The configured ceiling.
        actual_value: The observed value that exceeded the limit.
        agent_role_id: The role_id of the agent that breached the limit.
    """

    def __init__(
        self,
        limit_type: LimitType,
        limit_value: float,
        actual_value: float,
        agent_role_id: str,
    ) -> None:
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.actual_value = actual_value
        self.agent_role_id = agent_role_id
        super().__init__(
            f"Agent {agent_role_id!r} exceeded limit {limit_type.value}: "
            f"limit={limit_value}, actual={actual_value}"
        )

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of this error."""
        return {
            "error": "LimitExceededError",
            "limit_type": self.limit_type.value,
            "limit_value": self.limit_value,
            "actual_value": self.actual_value,
            "agent_role_id": self.agent_role_id,
        }
