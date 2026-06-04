"""
AlertRepository — IAlertFatigueRepository + write methods implementation.

Satisfies all anti-fatigue gate read methods and provides insert_alert /
insert_silent_log for the dispatch path.  Every query includes tenant_id
in the WHERE clause (REQ-N-006).
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.models import AlertRow, AlertStatus, BudgetState

logger = logging.getLogger(__name__)

# Budget defaults when the user has no settings row
_DEFAULT_DAILY_BUDGET_USD = 10.0
_DEFAULT_ALERT_THRESHOLD_PCT = 80.0
_DEFAULT_HARD_STOP_PCT = 100.0


class AlertRepository:
    """SQLAlchemy 2.0 async implementation of fatigue reads and alert writes.

    Args:
        session: Async SQLAlchemy session (injected by caller).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IAlertFatigueRepository ───────────────────────────────────────────────

    async def count_dispatched_today(self, user_id: UUID, tenant_id: UUID) -> int:
        """Count dispatched alerts for *user_id* since UTC midnight today."""
        stmt = text(
            """
            SELECT COUNT(*)
            FROM alert
            WHERE user_id  = :user_id
              AND tenant_id = :tenant_id
              AND status    = 'dispatched'
              AND dispatched_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
            """
        )
        result = await self._session.execute(
            stmt, {"user_id": user_id, "tenant_id": tenant_id}
        )
        return int(result.scalar() or 0)

    async def get_last_dispatch_for_ticker(
        self, user_id: UUID, ticker: str, tenant_id: UUID
    ) -> datetime | None:
        """Return the most recent dispatched_at for alerts matching *ticker*.

        The alert table stores alert_text; ticker matching is done via a
        LIKE check on the ticker symbol that appeared in the alert.  For a
        production deployment this would join event_exposure, but the alert
        table approach avoids a cross-table join on a hot path.
        """
        stmt = text(
            """
            SELECT MAX(dispatched_at)
            FROM alert
            WHERE user_id  = :user_id
              AND tenant_id = :tenant_id
              AND status    = 'dispatched'
              AND alert_text ILIKE :ticker_pattern
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "ticker_pattern": f"%{ticker}%",
            },
        )
        value = result.scalar()
        if value is None:
            return None
        # Ensure timezone-aware
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    async def get_recent_event_alert_ids(
        self,
        event_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        window_minutes: int,
    ) -> list[UUID]:
        """Return alert_ids for *event_id* within *window_minutes* for *user_id*."""
        stmt = text(
            """
            SELECT alert_id
            FROM alert
            WHERE event_id  = :event_id
              AND user_id   = :user_id
              AND tenant_id = :tenant_id
              AND created_at >= NOW() - (:window_minutes * INTERVAL '1 minute')
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "event_id": event_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "window_minutes": window_minutes,
            },
        )
        return [UUID(str(row[0])) for row in result.fetchall()]

    async def get_budget_state(self, user_id: UUID, tenant_id: UUID) -> BudgetState:
        """Read budget config from user.settings JSONB and today's spend."""
        settings_stmt = text(
            """
            SELECT
                COALESCE((settings->>'daily_budget_usd')::FLOAT, :default_budget)    AS daily_budget_usd,
                COALESCE((settings->>'alert_threshold_pct')::FLOAT, :default_thresh) AS alert_threshold_pct,
                COALESCE((settings->>'hard_stop_pct')::FLOAT, :default_hard_stop)    AS hard_stop_pct
            FROM "user"
            WHERE user_id   = :user_id
              AND tenant_id = :tenant_id
            LIMIT 1
            """
        )
        result = await self._session.execute(
            settings_stmt,
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "default_budget": _DEFAULT_DAILY_BUDGET_USD,
                "default_thresh": _DEFAULT_ALERT_THRESHOLD_PCT,
                "default_hard_stop": _DEFAULT_HARD_STOP_PCT,
            },
        )
        row = result.mappings().first()
        if row is None:
            daily_budget_usd = _DEFAULT_DAILY_BUDGET_USD
            alert_threshold_pct = _DEFAULT_ALERT_THRESHOLD_PCT
            hard_stop_pct = _DEFAULT_HARD_STOP_PCT
        else:
            daily_budget_usd = float(row["daily_budget_usd"])
            alert_threshold_pct = float(row["alert_threshold_pct"])
            hard_stop_pct = float(row["hard_stop_pct"])

        spent_today = await self.get_spent_today_usd(user_id, tenant_id)
        return BudgetState(
            daily_budget_usd=daily_budget_usd,
            spent_today_usd=spent_today,
            alert_threshold_pct=alert_threshold_pct,
            hard_stop_pct=hard_stop_pct,
        )

    async def get_spent_today_usd(self, user_id: UUID, tenant_id: UUID) -> float:
        """Return total cost_usd for today's dispatched alerts."""
        stmt = text(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM alert
            WHERE user_id   = :user_id
              AND tenant_id = :tenant_id
              AND status    = 'dispatched'
              AND dispatched_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
            """
        )
        result = await self._session.execute(
            stmt, {"user_id": user_id, "tenant_id": tenant_id}
        )
        return float(result.scalar() or 0.0)

    # ── Write methods ─────────────────────────────────────────────────────────

    async def insert_alert(self, alert_row: AlertRow) -> UUID:
        """Insert a dispatched alert row and return its alert_id.

        Args:
            alert_row: Fully populated AlertRow (including alert_id).

        Returns:
            The alert_id that was inserted.
        """
        stmt = text(
            """
            INSERT INTO alert (
                alert_id, event_id, user_id, tenant_id, rule_id,
                alert_text, action_signal, confidence, sample_size,
                dispatched_at, channel, cost_usd, status
            ) VALUES (
                :alert_id, :event_id, :user_id, :tenant_id, :rule_id,
                :alert_text, :action_signal, :confidence, :sample_size,
                :dispatched_at, :channel, :cost_usd, :status
            )
            """
        )
        await self._session.execute(
            stmt,
            {
                "alert_id": alert_row.alert_id,
                "event_id": alert_row.event_id,
                "user_id": alert_row.user_id,
                "tenant_id": alert_row.tenant_id,
                "rule_id": alert_row.rule_id,
                "alert_text": alert_row.alert_text,
                "action_signal": alert_row.action_signal.value if alert_row.action_signal else None,
                "confidence": alert_row.confidence,
                "sample_size": alert_row.sample_size,
                "dispatched_at": alert_row.dispatched_at,
                "channel": alert_row.channel,
                "cost_usd": alert_row.cost_usd,
                "status": alert_row.status.value,
            },
        )
        logger.debug("AlertRepository.insert_alert: inserted alert_id=%s", alert_row.alert_id)
        return alert_row.alert_id

    async def insert_silent_log(
        self,
        event_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        rule_id: UUID | None,
        status: AlertStatus,
    ) -> UUID:
        """Insert a minimal silent-log alert row with channel='silent'.

        Args:
            event_id: Source event.
            user_id: Affected user.
            tenant_id: Tenant scope.
            rule_id: Matched rule (may be None for pipeline-level silents).
            status: Suppression reason.

        Returns:
            The generated alert_id.
        """
        alert_id = uuid_lib.uuid4()
        stmt = text(
            """
            INSERT INTO alert (
                alert_id, event_id, user_id, tenant_id, rule_id,
                channel, cost_usd, status
            ) VALUES (
                :alert_id, :event_id, :user_id, :tenant_id, :rule_id,
                'silent', 0, :status
            )
            """
        )
        await self._session.execute(
            stmt,
            {
                "alert_id": alert_id,
                "event_id": event_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "rule_id": rule_id,
                "status": status.value,
            },
        )
        logger.debug(
            "AlertRepository.insert_silent_log: event=%s user=%s status=%s",
            event_id,
            user_id,
            status.value,
        )
        return alert_id
