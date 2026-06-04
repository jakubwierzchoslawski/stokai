"""
src.ai.cost.workflow_cost_guard — WorkflowCostGuard: per-workflow ceiling enforcer (PLAN-N-004).

Shared across all five Mode B workflows.  Replaces per-workflow ad-hoc guards
introduced by PLAN-F-006 (Morning Brief) and PLAN-F-008 (Watchlist Scan).

Key design decisions:
  - Uses decimal.Decimal internally to prevent float accumulation drift across
    up to 7 agent invocations per workflow run.
  - Emits a structured WARNING log at 80% of ceiling (once per run).
  - Raises WorkflowBudgetExceededError at 100% of ceiling.
  - Writes accumulated cost back to state.cost_usd as float (Pydantic/JSON compat).
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from typing import TYPE_CHECKING
from uuid import UUID

from src.ai.cost.errors import WorkflowBudgetExceededError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_WARN_THRESHOLD_PCT = Decimal("80")
_CEILING_PCT = Decimal("100")


class WorkflowCostGuard:
    """Enforces a per-workflow cost ceiling for all Mode B workflows.

    Uses Decimal internally to avoid float drift across 6-7 agent invocations.
    Instantiate once per workflow run; share across all AgentNode wrappers.

    Usage inside any AgentNode wrapper::

        guard = WorkflowCostGuard("morning_brief", 2.00, state.workflow_id)
        # after each agent completes:
        guard.check_and_accumulate(state, agent_cost_usd)

    Args:
        workflow_type: Workflow type string for structured log/error messages.
        ceiling_usd: Hard cost ceiling in USD (read from workflow YAML).
        workflow_id: UUID of the current workflow run (for error context).

    Raises:
        ValueError: If ceiling_usd is not positive (misconfiguration guard).
    """

    def __init__(
        self,
        workflow_type: str,
        ceiling_usd: float,
        workflow_id: UUID,
    ) -> None:
        if ceiling_usd <= 0:
            raise ValueError(
                f"ceiling_usd must be positive, got {ceiling_usd!r}"
            )
        self._workflow_type = workflow_type
        self._ceiling = Decimal(str(ceiling_usd))
        self._workflow_id = workflow_id
        self._warned: bool = False  # emit 80% WARNING at most once per run

    @property
    def ceiling_usd(self) -> float:
        """Return the configured ceiling in USD as float."""
        return float(self._ceiling)

    def check_and_accumulate(self, state: object, agent_cost_usd: float) -> None:
        """Accumulate agent cost into state, then check against ceiling.

        Converts both the existing state.cost_usd and agent_cost_usd to Decimal
        for accumulation to avoid IEEE-754 rounding drift.  Writes the result
        back to state.cost_usd as float for JSON/Pydantic compatibility.

        Emits a WARNING log at >= 80% of ceiling (once per run).
        Raises WorkflowBudgetExceededError at >= 100% of ceiling.

        Args:
            state: Any object with a mutable ``cost_usd: float`` attribute.
            agent_cost_usd: Cost in USD from the most recent agent invocation.

        Raises:
            WorkflowBudgetExceededError: When accumulated cost >= ceiling.
        """
        prior = Decimal(str(getattr(state, "cost_usd", 0.0)))
        increment = Decimal(str(agent_cost_usd))
        accumulated = prior + increment

        # Write back to state before raising so callers see updated cost on exception
        state.cost_usd = float(accumulated)  # type: ignore[attr-defined]

        # Use ROUND_DOWN (floor) to avoid false-positive ceiling breach due to
        # Decimal string-precision representation of per-agent cost inputs.
        pct = (accumulated / self._ceiling * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )

        if pct >= _CEILING_PCT:
            logger.error(
                "WorkflowCostGuard: ceiling EXCEEDED workflow_type=%r workflow_id=%s "
                "accumulated_usd=%.4f ceiling_usd=%.4f pct_used=%.2f",
                self._workflow_type,
                self._workflow_id,
                float(accumulated),
                float(self._ceiling),
                float(pct),
            )
            raise WorkflowBudgetExceededError(
                workflow_type=self._workflow_type,
                ceiling_usd=float(self._ceiling),
                accumulated_usd=float(accumulated),
                workflow_id=self._workflow_id,
            )

        if pct >= _WARN_THRESHOLD_PCT and not self._warned:
            self._warned = True
            logger.warning(
                "WorkflowCostGuard: cost_ceiling_approach workflow_type=%r "
                "workflow_id=%s accumulated_usd=%.4f ceiling_usd=%.4f pct_used=%.2f",
                self._workflow_type,
                self._workflow_id,
                float(accumulated),
                float(self._ceiling),
                float(pct),
            )
