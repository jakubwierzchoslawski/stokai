"""
AlertRuleRepository — IAlertRuleRepository implementation.

Single-query implementation: joins alert_rule with the user table to fetch
user_email without a follow-up query (no N+1).  All queries are scoped to
tenant_id (REQ-N-006).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.models import AlertRuleRow

logger = logging.getLogger(__name__)


class AlertRuleRepository:
    """SQLAlchemy 2.0 async implementation of IAlertRuleRepository.

    Args:
        session: Async SQLAlchemy session (injected by caller).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_rules(self, tenant_id: UUID) -> list[AlertRuleRow]:
        """Return all enabled alert rules for *tenant_id*, joined with user email.

        Single parameterised query — indexed on (tenant_id, enabled).
        Parsing of JSONB columns (event_categories, ticker_list) is handled
        here so callers always receive typed Python lists.

        Args:
            tenant_id: Tenant whose rules to load.

        Returns:
            List of AlertRuleRow (may be empty).
        """
        stmt = text(
            """
            SELECT
                ar.rule_id,
                ar.tenant_id,
                ar.user_id,
                u.email          AS user_email,
                ar.event_categories,
                ar.intensity_min,
                ar.ticker_list,
                ar.quiet_hours_start,
                ar.quiet_hours_end,
                ar.daily_limit,
                ar.dedup_window_minutes,
                ar.per_ticker_interval_hours,
                ar.enabled
            FROM alert_rule ar
            JOIN "user" u ON u.user_id = ar.user_id
            WHERE ar.tenant_id = :tenant_id
              AND ar.enabled = TRUE
            ORDER BY ar.created_at ASC
            """
        )
        result = await self._session.execute(stmt, {"tenant_id": tenant_id})
        rows = result.mappings().all()

        rules: list[AlertRuleRow] = []
        for row in rows:
            rules.append(
                AlertRuleRow(
                    rule_id=row["rule_id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    user_email=row["user_email"],
                    event_categories=list(row["event_categories"] or []),
                    intensity_min=row["intensity_min"],
                    ticker_list=list(row["ticker_list"] or []),
                    quiet_hours_start=row["quiet_hours_start"],
                    quiet_hours_end=row["quiet_hours_end"],
                    daily_limit=row["daily_limit"],
                    dedup_window_minutes=row["dedup_window_minutes"],
                    per_ticker_interval_hours=row["per_ticker_interval_hours"],
                    enabled=row["enabled"],
                )
            )

        logger.debug(
            "AlertRuleRepository.get_active_rules: tenant=%s returned %d rules",
            tenant_id,
            len(rules),
        )
        return rules
