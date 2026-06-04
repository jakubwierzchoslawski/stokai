"""
AlertRuleEvaluator — IAlertRuleEvaluator implementation.

Filters active alert rules by intensity, category, and ticker membership.
Anti-fatigue gating is NOT applied here — that is the AlertDispatcher's
responsibility.  Must complete in ≤1s (enforced by single DB call in repo).
"""
from __future__ import annotations

import logging
from uuid import UUID

from src.alerts.interfaces.i_alert_rule_evaluator import IAlertRuleEvaluator, RuleMatch
from src.alerts.interfaces.i_alert_rule_repository import IAlertRuleRepository
from src.alerts.models import AlertRuleRow

logger = logging.getLogger(__name__)


class AlertRuleEvaluator:
    """Evaluates active alert rules against an incoming event.

    Constructor accepts only IAlertRuleRepository (DIP). All filter logic
    is pure Python on the in-memory rule list — no additional DB round-trips.

    Args:
        rule_repo: Repository for fetching active rules per tenant.
    """

    def __init__(self, rule_repo: IAlertRuleRepository) -> None:
        self._rule_repo = rule_repo

    # ── IAlertRuleEvaluator ───────────────────────────────────────────────────

    async def evaluate(
        self,
        event_id: UUID,
        intensity: int,
        categories: list[str],
        matched_tickers: list[str],
        tenant_id: UUID | None,
    ) -> list[RuleMatch]:
        """Evaluate all active rules and return matches.

        Filters:
        1. intensity >= rule.intensity_min
        2. If rule.event_categories is non-empty, at least one category must match.
        3. If rule.ticker_list is non-empty, at least one ticker must match.

        Args:
            event_id: UUID of the processed event (for logging only).
            intensity: Classified event intensity (1–5).
            categories: Event category labels from classification.
            matched_tickers: Tickers extracted from the event.
            tenant_id: Owning tenant, or None for global events.

        Returns:
            List of RuleMatch objects for rules that passed all filters.
            matched_tickers on each RuleMatch is the intersection of event
            tickers and rule.ticker_list (or all event tickers if rule has no
            ticker constraint).
        """
        if tenant_id is None:
            logger.debug(
                "AlertRuleEvaluator.evaluate: tenant_id=None for event=%s — "
                "returning empty list (no global-event rule support yet)",
                event_id,
            )
            return []

        rules = await self._rule_repo.get_active_rules(tenant_id)
        if not rules:
            return []

        category_set = set(categories)
        ticker_set = set(matched_tickers)

        matches: list[RuleMatch] = []
        for rule in rules:
            # Filter 1: intensity
            if intensity < rule.intensity_min:
                continue

            # Filter 2: event categories (empty rule.event_categories = wildcard)
            if rule.event_categories:
                if not set(rule.event_categories).intersection(category_set):
                    continue

            # Filter 3: ticker list (empty rule.ticker_list = wildcard)
            if rule.ticker_list:
                rule_tickers = set(rule.ticker_list)
                intersection = rule_tickers.intersection(ticker_set)
                if not intersection:
                    continue
                # matched_tickers on the RuleMatch is the intersection
                effective_tickers = list(intersection)
            else:
                # No ticker constraint — pass all event tickers
                effective_tickers = list(matched_tickers)

            matches.append(
                RuleMatch(
                    rule_id=rule.rule_id,
                    user_id=rule.user_id,
                    user_email=rule.user_email,
                    tenant_id=rule.tenant_id,
                    channels=["email"],  # default channel; extend when multi-channel rules added
                    matched_tickers=effective_tickers,
                )
            )

        logger.debug(
            "AlertRuleEvaluator.evaluate: event=%s tenant=%s intensity=%d "
            "rules_checked=%d rules_matched=%d",
            event_id,
            tenant_id,
            intensity,
            len(rules),
            len(matches),
        )
        return matches
