"""
Shared base logic for AgentNode wrappers.

Each node:
  1. Resolves AgentDefinition from IAgentRegistry.
  2. ToolGuard.assert_allowed for each tool.
  3. Wraps LLM call in LangfuseInvocationLogger.
  4. ExecutionLimiter checks.
  5. Accumulates cost_usd + tokens_consumed.
  6. Validates output against AgentDefinition.output_schema (output must not be None).
  7. Writes to the correct state field.
  8. Records in confidence_scores.
  9. CostCeilingGuard.check(state) as final step.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


class AgentOutputValidationError(Exception):
    """Raised when an agent returns an output that fails schema validation."""

    def __init__(self, role_id: str, reason: str) -> None:
        super().__init__(f"Agent {role_id!r} output validation failed: {reason}")
        self.role_id = role_id
        self.reason = reason


def _validate_output(role_id: str, output: Any) -> None:
    """Validate that the agent output is not None.

    A None output indicates the agent failed to produce a valid response.
    Full JSON-schema validation is intentionally minimal in this MVP
    implementation — the output_schema field from AgentDefinition is reserved
    for future OpenAPI-based validation.

    Raises:
        AgentOutputValidationError: If output is None.
    """
    if output is None:
        raise AgentOutputValidationError(
            role_id=role_id,
            reason="output is None; agent must return a non-null dict",
        )


def _accumulate_cost(
    state: WorkflowState,
    cost_usd: float,
    input_tokens: int,
    output_tokens: int,
    role_id: str,
) -> dict:
    """Return updated fields for cost_usd and tokens_consumed."""
    new_tokens = dict(state.tokens_consumed)
    new_tokens[f"{role_id}_input"] = new_tokens.get(f"{role_id}_input", 0) + input_tokens
    new_tokens[f"{role_id}_output"] = (
        new_tokens.get(f"{role_id}_output", 0) + output_tokens
    )
    return {
        "cost_usd": state.cost_usd + cost_usd,
        "tokens_consumed": new_tokens,
    }
