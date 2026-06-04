"""
AlertRuleEvaluator — IAlertRuleEvaluator implementation.

Evaluates active alert rules with:
- Intensity filtering (rule.min_intensity <= classification.intensity)
- 60-minute deduplication window per (event_id, rule_id, user_id)
- Daily push limit (default: 5 alerts per user per day)
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.events.models import ClassificationResult, ExposureCandidate

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_MINUTES = 60
_DAILY_PUSH_LIMIT = 5


class AlertRuleEvaluator:
    """Evaluates alert rules with intensity, deduplication, and anti-fatigue controls.

    Args:
        session: Async SQLAlchemy session for rule and alert queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IAlertRuleEvaluator ───────────────────────────────────────────────────

    async def evaluate(
        self,
        event_id: UUID,
        classification: ClassificationResult,
        exposures: list[ExposureCandidate],
        tenant_id: UUID | None,
    ) -> list[RuleMatch]:
        """Evaluate alert rules for the given event.

        Returns only rules that pass intensity, dedup, and anti-fatigue checks.
        """
        # 1. Fetch active rules for the tenant
        rules_stmt = text(
            """
            SELECT
                ar.rule_id,
                ar.user_id,
                ar.tenant_id,
                ar.min_intensity,
                ar.company_scope,
                ar.channels
            FROM alert_rule ar
            WHERE
                ar.is_active = true
                AND (:tenant_id IS NULL OR ar.tenant_id = :tenant_id)
            """
        )
        result = await self._session.execute(rules_stmt, {"tenant_id": tenant_id})
        rules = list(result.mappings())

        matched: list[RuleMatch] = []
        exposed_company_ids = {str(e.company_id) for e in exposures}

        for rule in rules:
            rule_id: UUID = rule["rule_id"]
            user_id: UUID = rule["user_id"]
            rule_tenant_id: UUID = rule["tenant_id"]
            min_intensity: int = rule["min_intensity"]
            company_scope: list = rule["company_scope"] or []
            channels: list[str] = rule["channels"] or ["email"]

            # 2. Intensity filter
            if classification.intensity < min_intensity:
                continue

            # 3. Scope filter — if rule has company scope, check intersection
            if company_scope:
                scope_ids = {str(c) for c in company_scope}
                if not scope_ids.intersection(exposed_company_ids):
                    continue

            # 4. Deduplication check
            dedup_stmt = text(
                """
                SELECT COUNT(*)
                FROM alert
                WHERE
                    rule_id = :rule_id
                    AND event_id = :event_id
                    AND sent_at > NOW() - INTERVAL ':window_minutes minutes'
                """
            )
            dedup_result = await self._session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM alert
                    WHERE rule_id = :rule_id
                      AND event_id = :event_id
                      AND sent_at > NOW() - (:window_minutes * INTERVAL '1 minute')
                    """
                ),
                {
                    "rule_id": rule_id,
                    "event_id": event_id,
                    "window_minutes": _DEDUP_WINDOW_MINUTES,
                },
            )
            if dedup_result.scalar() > 0:
                logger.debug(
                    "Dedup: rule %s already fired for event %s within %dm window",
                    rule_id,
                    event_id,
                    _DEDUP_WINDOW_MINUTES,
                )
                continue

            # 5. Anti-fatigue daily limit check
            daily_stmt = text(
                """
                SELECT COUNT(*) FROM alert
                WHERE user_id = :user_id
                  AND sent_at > NOW() - INTERVAL '1 day'
                """
            )
            daily_result = await self._session.execute(
                daily_stmt, {"user_id": user_id}
            )
            if daily_result.scalar() >= _DAILY_PUSH_LIMIT:
                logger.debug(
                    "Anti-fatigue: user %s has reached daily limit of %d alerts",
                    user_id,
                    _DAILY_PUSH_LIMIT,
                )
                continue

            matched.append(
                RuleMatch(
                    rule_id=rule_id,
                    user_id=user_id,
                    tenant_id=rule_tenant_id,
                    channels=channels,
                )
            )

        return matched
