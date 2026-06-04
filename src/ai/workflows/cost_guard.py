"""
ai.workflows.cost_guard — CostCeilingGuard for per-run cost enforcement.

REQ-N-004: every AI workflow run must not exceed a configurable cost ceiling.
The guard is called after every AgentNode to check accumulated cost.
"""
from __future__ import annotations

from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.state import WorkflowState


class CostCeilingGuard:
    """Enforces a per-run cost ceiling.

    Inject into each AgentNode at graph-build time.  Call check(state) after
    every LLM call to halt the workflow if the ceiling is reached.

    Raises:
        ValueError: if ceiling_usd is not positive (misconfiguration guard).
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

    def check(self, state: WorkflowState) -> None:
        """Raise WorkflowCostLimitError if state.cost_usd has reached the ceiling.

        The check uses >= so that a run that lands exactly on the ceiling is
        also terminated (fail-safe for the $1.50 budget constraint).
        """
        if state.cost_usd >= self._ceiling:
            raise WorkflowCostLimitError(
                accumulated=state.cost_usd,
                ceiling=self._ceiling,
                workflow_id=state.workflow_id,
            )
