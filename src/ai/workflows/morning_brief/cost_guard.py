"""
src.ai.workflows.morning_brief.cost_guard — CostGuard for Morning Brief.

Enforces the per-workflow $2.00 cost ceiling (REQ-N-004) at runtime:
  - Below 80%: no action.
  - At 80%: logs WARNING; injects token_budget_override into state.
  - At 100%: raises WorkflowCostCeilingExceeded; graph routes to block_and_log.

MorningBriefGraph wraps each AgentNode call in CostGuard.check() via a
decorator pattern so node function signatures remain unchanged.

PLAN-F-006 TASK-014
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief_nodes import WorkflowCostCeilingExceeded

logger = logging.getLogger(__name__)

_WARN_THRESHOLD = 0.80
_BLOCK_THRESHOLD = 1.00

# Reduction factor applied to remaining agent token budgets at 80% ceiling
_TOKEN_BUDGET_REDUCTION_FACTOR = 0.5


class CostGuard:
    """Enforces per-workflow cost ceiling for the Morning Brief.

    Args:
        cost_ceiling_usd: Maximum allowed cost per workflow run (default $2.00).

    Usage:
        guard = CostGuard(cost_ceiling_usd=2.00)
        # After each agent node:
        guard.check(updated_state)
    """

    def __init__(self, cost_ceiling_usd: float = 2.00) -> None:
        if cost_ceiling_usd <= 0:
            raise ValueError(
                f"cost_ceiling_usd must be positive, got {cost_ceiling_usd!r}"
            )
        self._ceiling = cost_ceiling_usd
        self._warned = False  # prevent duplicate WARNING logs

    @property
    def cost_ceiling_usd(self) -> float:
        return self._ceiling

    def check(self, state: MorningBriefState) -> MorningBriefState:
        """Check accumulated cost against ceiling thresholds.

        At 80%: logs WARNING; calls reduce_token_budgets().
        At 100%: raises WorkflowCostCeilingExceeded.

        Args:
            state: Current MorningBriefState after an agent node.

        Returns:
            Updated state (may have token_budget_override injected at 80%).

        Raises:
            WorkflowCostCeilingExceeded: When cost >= ceiling.
        """
        ratio = state.cost_usd / self._ceiling if self._ceiling > 0 else 1.0

        if ratio >= _BLOCK_THRESHOLD:
            logger.error(
                "CostGuard: CEILING EXCEEDED $%.4f >= $%.2f for workflow_id=%s",
                state.cost_usd,
                self._ceiling,
                state.workflow_id,
            )
            raise WorkflowCostCeilingExceeded(
                accumulated=state.cost_usd,
                ceiling=self._ceiling,
                workflow_id=state.workflow_id,
            )

        if ratio >= _WARN_THRESHOLD and not self._warned:
            self._warned = True
            logger.warning(
                "CostGuard: cost_ceiling_approach — accumulated $%.4f is %.0f%% of "
                "ceiling $%.2f for workflow_id=%s — reducing remaining token budgets",
                state.cost_usd,
                ratio * 100,
                self._ceiling,
                state.workflow_id,
            )
            state = self.reduce_token_budgets(state)

        return state

    def reduce_token_budgets(
        self,
        state: MorningBriefState,
        remaining_agents: list[str] | None = None,
    ) -> MorningBriefState:
        """Inject a token_budget_override dict into state.

        Halves the default token budget for each remaining agent. This signals
        to AgentNode wrappers that they should request fewer tokens.

        Args:
            state: Current MorningBriefState.
            remaining_agents: List of remaining agent role IDs. If None,
                a default set is used.

        Returns:
            Updated state with token_budget_override populated.
        """
        _remaining = remaining_agents or [
            "historical_context_agent",
            "recommendation_synthesizer",
            "evaluate_quality",
            "narrative_writer",
        ]

        # Default token budgets per agent role (conservative estimates)
        _defaults = {
            "historical_context_agent": 4096,
            "recommendation_synthesizer": 2048,
            "evaluate_quality": 2048,
            "narrative_writer": 4096,
        }

        override = {
            agent: int(_defaults.get(agent, 2048) * _TOKEN_BUDGET_REDUCTION_FACTOR)
            for agent in _remaining
        }

        logger.debug(
            "CostGuard.reduce_token_budgets: injecting overrides %s", override
        )

        return state.model_copy(
            update={"inputs": {**state.inputs, "token_budget_override": override}}
        )


def cost_guard_decorator(guard: CostGuard) -> Callable:
    """Decorator factory that wraps an async AgentNode with CostGuard.check().

    Usage:
        guarded_node = cost_guard_decorator(guard)(relevance_analyst_node)

    The node function signature is unchanged.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: MorningBriefState, **kwargs) -> MorningBriefState:
            result = await fn(state, **kwargs)
            result = guard.check(result)
            return result
        return wrapper
    return decorator
