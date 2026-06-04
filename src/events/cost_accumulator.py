"""
CostAccumulator — tracks running per-event LLM/API cost.

Thread-unsafe by design: a single CostAccumulator instance lives inside one
PipelineContext and is never shared across concurrent runs.
"""
from __future__ import annotations

from src.event_pipeline.pricing import LLMPricingTable
from src.events.exceptions import CostCeilingExceededError


class CostAccumulator:
    """Accumulates per-step costs and enforces a per-event ceiling.

    Usage::

        acc = CostAccumulator()
        acc.add(0.002)
        acc.check_ceiling(0.05)   # raises CostCeilingExceededError if total > 0.05

        # Convenience — compute + add in one call:
        cost = acc.add_from_tokens("claude-haiku-4-5", 1000, 100)
    """

    def __init__(self) -> None:
        self._total: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, cost_usd: float) -> None:
        """Add *cost_usd* to the running total.

        Args:
            cost_usd: Non-negative cost in USD for the most recent step.
        """
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative, got {cost_usd}")
        self._total += cost_usd

    def check_ceiling(self, ceiling: float) -> None:
        """Raise :class:`CostCeilingExceededError` if running total exceeds *ceiling*.

        The check is exclusive: ``total > ceiling`` raises, ``total == ceiling`` does NOT.

        Args:
            ceiling: Maximum allowed cost in USD (e.g. 0.05).

        Raises:
            CostCeilingExceededError: When ``self.total > ceiling``, carrying
                ``accumulated_usd`` and ``ceiling_usd`` attributes.
        """
        if self._total > ceiling:
            raise CostCeilingExceededError(
                f"Per-event cost ceiling of ${ceiling:.4f} exceeded "
                f"(current total: ${self._total:.4f})",
                accumulated_usd=self._total,
                ceiling_usd=ceiling,
            )

    def add_from_tokens(
        self, model_id: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Compute cost via :class:`LLMPricingTable`, add it, and return it.

        Convenience wrapper that eliminates the caller having to import the
        pricing table separately.

        Args:
            model_id: One of the keys in MODEL_PRICES (e.g. ``"claude-haiku-4-5"``).
            input_tokens: Number of prompt/input tokens (must be >= 0).
            output_tokens: Number of completion/output tokens (must be >= 0).

        Returns:
            The computed cost in USD (also added to the running total).

        Raises:
            ValueError: Propagated from :meth:`LLMPricingTable.compute` for unknown
                model_id or negative token counts.
        """
        cost = LLMPricingTable.compute(model_id, input_tokens, output_tokens)
        self.add(cost)
        return cost

    @property
    def total(self) -> float:
        """Current running total in USD."""
        return self._total
