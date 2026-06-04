"""
AlertRuleCrudRepository — full CRUD for alert_rule rows (Alerts Center, PLAN-F-025).

Provides get_by_user, get_by_id (returns None not raise), insert, update (partial),
and delete (hard).  All queries are scoped to user_id + tenant_id.
"""
from __future__ import annotations

import logging
import uuid as uuid_lib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.exceptions import NotFoundError
from src.alerts.schemas import AlertRuleResponse

logger = logging.getLogger(__name__)


class AlertRuleCrudRepository:
    """SQLAlchemy 2.0 async CRUD for alert_rule.

    Args:
        session: Async SQLAlchemy session (injected by caller).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_response(row) -> AlertRuleResponse:
        return AlertRuleResponse(
            rule_id=row["rule_id"],
            user_id=row["user_id"],
            name=row["name"],
            enabled=row["enabled"],
            event_category_filter=list(row["event_category_filter"] or []),
            intensity_min=row["intensity_min"],
            ticker_list=list(row["ticker_list"] or []),
            quiet_hours_start=row["quiet_hours_start"],
            quiet_hours_end=row["quiet_hours_end"],
            per_ticker_interval_hours=row["per_ticker_interval_hours"],
            channels=list(row["channels"] or []),
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_user(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> list[AlertRuleResponse]:
        """Return all alert rules owned by *user_id* within *tenant_id*."""
        stmt = text(
            """
            SELECT
                rule_id, user_id, tenant_id, name, enabled,
                event_category_filter, intensity_min, ticker_list,
                quiet_hours_start, quiet_hours_end,
                per_ticker_interval_hours, channels
            FROM alert_rule
            WHERE user_id   = :user_id
              AND tenant_id = :tenant_id
            ORDER BY created_at ASC
            """
        )
        result = await self._session.execute(
            stmt, {"user_id": user_id, "tenant_id": tenant_id}
        )
        rows = result.mappings().all()
        return [self._row_to_response(r) for r in rows]

    async def get_by_id(
        self, *, rule_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> AlertRuleResponse | None:
        """Return a single rule or None if not found / wrong owner."""
        stmt = text(
            """
            SELECT
                rule_id, user_id, tenant_id, name, enabled,
                event_category_filter, intensity_min, ticker_list,
                quiet_hours_start, quiet_hours_end,
                per_ticker_interval_hours, channels
            FROM alert_rule
            WHERE rule_id   = :rule_id
              AND user_id   = :user_id
              AND tenant_id = :tenant_id
            LIMIT 1
            """
        )
        result = await self._session.execute(
            stmt, {"rule_id": rule_id, "user_id": user_id, "tenant_id": tenant_id}
        )
        row = result.mappings().first()
        if row is None:
            return None
        return self._row_to_response(row)

    # ── Write ─────────────────────────────────────────────────────────────────

    async def insert(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        name: str,
        event_category_filter: list[str],
        intensity_min: int,
        ticker_list: list[str],
        quiet_hours_start: str | None,
        quiet_hours_end: str | None,
        per_ticker_interval_hours: int,
        channels: list[str],
    ) -> UUID:
        """Insert a new alert rule and return its generated UUID."""
        import json

        rule_id = uuid_lib.uuid4()
        stmt = text(
            """
            INSERT INTO alert_rule (
                rule_id, user_id, tenant_id, name, enabled,
                event_category_filter, intensity_min, ticker_list,
                quiet_hours_start, quiet_hours_end,
                per_ticker_interval_hours, channels
            ) VALUES (
                :rule_id, :user_id, :tenant_id, :name, TRUE,
                :event_category_filter::jsonb, :intensity_min, :ticker_list::jsonb,
                :quiet_hours_start, :quiet_hours_end,
                :per_ticker_interval_hours, :channels::jsonb
            )
            """
        )
        await self._session.execute(
            stmt,
            {
                "rule_id": rule_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "name": name,
                "event_category_filter": json.dumps(event_category_filter),
                "intensity_min": intensity_min,
                "ticker_list": json.dumps(ticker_list),
                "quiet_hours_start": quiet_hours_start,
                "quiet_hours_end": quiet_hours_end,
                "per_ticker_interval_hours": per_ticker_interval_hours,
                "channels": json.dumps(channels),
            },
        )
        logger.debug("AlertRuleCrudRepository.insert: rule_id=%s user=%s", rule_id, user_id)
        return rule_id

    async def update(
        self,
        *,
        rule_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        name: str | None = None,
        enabled: bool | None = None,
        event_category_filter: list[str] | None = None,
        intensity_min: int | None = None,
        ticker_list: list[str] | None = None,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        per_ticker_interval_hours: int | None = None,
        channels: list[str] | None = None,
    ) -> None:
        """Partial update — only provided fields are set.

        Uses explicit COALESCE so unset fields remain unchanged in the DB.
        """
        import json

        params: dict = {
            "rule_id": rule_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "name": name,
            "enabled": enabled,
            "event_category_filter": json.dumps(event_category_filter) if event_category_filter is not None else None,
            "intensity_min": intensity_min,
            "ticker_list": json.dumps(ticker_list) if ticker_list is not None else None,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
            "per_ticker_interval_hours": per_ticker_interval_hours,
            "channels": json.dumps(channels) if channels is not None else None,
        }

        stmt = text(
            """
            UPDATE alert_rule SET
                name                   = COALESCE(:name, name),
                enabled                = COALESCE(:enabled, enabled),
                event_category_filter  = COALESCE(:event_category_filter::jsonb, event_category_filter),
                intensity_min          = COALESCE(:intensity_min, intensity_min),
                ticker_list            = COALESCE(:ticker_list::jsonb, ticker_list),
                quiet_hours_start      = CASE WHEN :quiet_hours_start IS NOT NULL THEN :quiet_hours_start ELSE quiet_hours_start END,
                quiet_hours_end        = CASE WHEN :quiet_hours_end IS NOT NULL THEN :quiet_hours_end ELSE quiet_hours_end END,
                per_ticker_interval_hours = COALESCE(:per_ticker_interval_hours, per_ticker_interval_hours),
                channels               = COALESCE(:channels::jsonb, channels),
                updated_at             = NOW()
            WHERE rule_id   = :rule_id
              AND user_id   = :user_id
              AND tenant_id = :tenant_id
            """
        )
        await self._session.execute(stmt, params)
        logger.debug("AlertRuleCrudRepository.update: rule_id=%s", rule_id)

    async def delete(
        self, *, rule_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> None:
        """Hard-delete an alert rule.

        Raises:
            NotFoundError: if no row was deleted (not found or wrong owner).
        """
        stmt = text(
            """
            DELETE FROM alert_rule
            WHERE rule_id   = :rule_id
              AND user_id   = :user_id
              AND tenant_id = :tenant_id
            """
        )
        result = await self._session.execute(
            stmt, {"rule_id": rule_id, "user_id": user_id, "tenant_id": tenant_id}
        )
        if result.rowcount == 0:
            raise NotFoundError("AlertRule", rule_id)
        logger.debug("AlertRuleCrudRepository.delete: rule_id=%s", rule_id)
