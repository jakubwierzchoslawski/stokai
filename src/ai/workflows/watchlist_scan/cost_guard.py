"""
ai.workflows.watchlist_scan.cost_guard — WorkflowCostGuard for per-run cost enforcement.

REQ-N-004: every watchlist scan run must not exceed $1.00.
The guard is instantiated once per workflow run and shared across all node invocations.

PLAN-F-008 TASK-011
"""
from __future__ import annotations

from uuid import UUID

from src.ai.workflows.watchlist_scan.state import WatchlistScanState


# ── WorkflowBudgetExceededError ───────────────────────────────────────────────


class WorkflowBudgetExceededError(Exception):
    """Raised by WorkflowCostGuard when the per-run cost ceiling is exceeded.

    Carries current_cost_usd, ceiling_usd, and workflow_id for diagnostics.
    """

    def __init__(
        self,
        current_cost_usd: float,
        ceiling_usd: float,
        workflow_id: UUID,
    ) -> None:
        super().__init__(
            f"Workflow {workflow_id} exceeded budget ceiling: "
            f"${current_cost_usd:.4f} > ${ceiling_usd:.4f}"
        )
        self.current_cost_usd = current_cost_usd
        self.ceiling_usd = ceiling_usd
        self.workflow_id = workflow_id

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of the error details."""
        return {
            "error": "WorkflowBudgetExceededError",
            "workflow_id": str(self.workflow_id),
            "current_cost_usd": self.current_cost_usd,
            "ceiling_usd": self.ceiling_usd,
        }


# ── WorkflowCostGuard ─────────────────────────────────────────────────────────


class WorkflowCostGuard:
    """Enforces a per-run cost ceiling for the Watchlist Scan workflow.

    Instantiated once per workflow run and shared across all node invocations.
    Call check_and_accumulate(state, agent_cost) after every LLM call.

    Raises:
        ValueError: if ceiling_usd is not positive (misconfiguration guard).
        WorkflowBudgetExceededError: if accumulated cost exceeds the ceiling.
    """

    def __init__(self, ceiling_usd: float) -> None:
        if ceiling_usd <= 0.0:
            raise ValueError(
                f"ceiling_usd must be a positive number, got {ceiling_usd!r}"
            )
        self._ceiling = ceiling_usd

    @property
    def ceiling_usd(self) -> float:
        return self._ceiling

    def check_and_accumulate(
        self,
        state: WatchlistScanState,
        agent_cost: float,
    ) -> None:
        """Accumulate agent_cost into state.cost_usd atomically, then check ceiling.

        Adds agent_cost to state.cost_usd in-place (state is mutable — frozen=False).
        Raises WorkflowBudgetExceededError if state.cost_usd > self.ceiling_usd.

        Note: the check is *strictly greater than* so a run that lands exactly on
        the ceiling is NOT terminated (ceiling is inclusive per AC-001).

        Args:
            state: Current WatchlistScanState (mutated in-place).
            agent_cost: The cost in USD from the most recent agent invocation.

        Raises:
            WorkflowBudgetExceededError: When state.cost_usd > self._ceiling.
        """
        state.cost_usd = state.cost_usd + agent_cost
        if state.cost_usd > self._ceiling:
            raise WorkflowBudgetExceededError(
                current_cost_usd=state.cost_usd,
                ceiling_usd=self._ceiling,
                workflow_id=state.workflow_id,
            )
