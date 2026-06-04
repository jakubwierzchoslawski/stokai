"""
IAlertRuleEvaluator — protocol for evaluating alert rules against a pipeline event.

Extended from PLAN-F-001: RuleMatch now carries user_email and matched_tickers
to support the dispatch path without additional DB lookups.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from typing_extensions import Protocol, runtime_checkable


class RuleMatch(BaseModel):
    """Describes a single alert rule that matched the current event."""

    rule_id: UUID
    user_id: UUID
    user_email: str           # added: dispatch path uses this directly
    tenant_id: UUID
    channels: list[str]
    matched_tickers: list[str]  # added: subset of event tickers that matched the rule


@runtime_checkable
class IAlertRuleEvaluator(Protocol):
    """Interface for applying alert rules against an incoming pipeline event.

    Implementations filter the active rule set by intensity, category, and
    ticker membership — anti-fatigue gating is handled downstream by
    AlertDispatcher / AntiFatigueChecker.
    """

    async def evaluate(
        self,
        event_id: UUID,
        intensity: int,
        categories: list[str],
        matched_tickers: list[str],
        tenant_id: UUID | None,
    ) -> list[RuleMatch]:
        """Evaluate all active alert rules for the given event.

        Args:
            event_id: UUID of the processed event.
            intensity: Classified event intensity (1–5).
            categories: Event category labels from classification.
            matched_tickers: Tickers extracted from the event.
            tenant_id: Owning tenant, or None for global events.

        Returns:
            List of rules that matched intensity, category, and ticker filters.
            Anti-fatigue suppression is NOT applied here.
            Returns an empty list when no rules fire.
        """
        ...
