"""
ai.workflows.event_deep_dive.cost_accumulator — mutable cost tracker with ceiling.

CostAccumulator is a mutable dataclass that tracks the total USD cost across
all agent calls in a single deep-dive workflow run.  It raises
CostCeilingExceededError BEFORE adding a new amount if the addition would
reach or exceed the configured ceiling.

PLAN-F-010 TASK-003.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError


@dataclass
class CostAccumulator:
    """Mutable accumulator for per-run LLM/API costs.

    Raises CostCeilingExceededError BEFORE adding an amount that would push
    total_usd >= ceiling_usd.  This means the amount is never committed when
    the ceiling would be crossed, keeping the state consistent for callers
    that catch the exception.

    Args:
        ceiling_usd: Maximum allowed total cost for a single workflow run.
    """

    ceiling_usd: float
    total_usd: float = field(default=0.0)

    def add(self, amount: float) -> None:
        """Add *amount* to total_usd after checking the ceiling.

        Raises CostCeilingExceededError BEFORE modifying total_usd if
        total_usd + amount >= ceiling_usd.

        Args:
            amount: Non-negative cost in USD to add.

        Raises:
            CostCeilingExceededError: If the addition would hit or exceed the ceiling.
            ValueError: If amount is negative.
        """
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount!r}")

        if self.total_usd + amount >= self.ceiling_usd:
            raise CostCeilingExceededError(
                cost_accumulated=self.total_usd,
                ceiling_usd=self.ceiling_usd,
            )

        self.total_usd += amount
