"""
AlertRepository — SQLAlchemy 2.0 async implementation of IAlertRepository.
"""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.interfaces.i_alert_repository import IAlertRepository


class AlertRepository:
    """Async SQLAlchemy repository for the alert table and silent-log records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IAlertRepository ──────────────────────────────────────────────────────

    async def insert_alert(
        self, alert_data: dict, cost_usd: float | None = None
    ) -> UUID:
        """Insert an alert row and return the generated alert_id.

        Args:
            alert_data: Dictionary of alert fields.
            cost_usd: Optional total LLM cost in USD for this pipeline run.
                      Written to the ``cost_usd`` column. NULL when not provided.
        """
        alert_id = alert_data.get("alert_id") or uuid.uuid4()
        # Prefer explicit cost_usd parameter; fall back to alert_data entry.
        resolved_cost = cost_usd if cost_usd is not None else alert_data.get("cost_usd")
        stmt = text(
            """
            INSERT INTO alert (
                alert_id,
                tenant_id,
                event_id,
                company_id,
                rule_id,
                channel,
                sent_at,
                content,
                confidence,
                cost_usd
            ) VALUES (
                :alert_id,
                :tenant_id,
                :event_id,
                :company_id,
                :rule_id,
                :channel,
                :sent_at,
                :content,
                :confidence,
                :cost_usd
            )
            ON CONFLICT (alert_id) DO NOTHING
            RETURNING alert_id
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "alert_id": alert_id,
                "tenant_id": alert_data.get("tenant_id"),
                "event_id": alert_data.get("event_id"),
                "company_id": alert_data.get("company_id"),
                "rule_id": alert_data.get("rule_id"),
                "channel": alert_data.get("channel", "email"),
                "sent_at": alert_data.get("sent_at"),
                "content": alert_data.get("content", ""),
                "confidence": alert_data.get("confidence", 1.0),
                "cost_usd": resolved_cost,
            },
        )
        await self._session.flush()
        returned = result.scalar_one_or_none()
        return returned if returned is not None else alert_id

    async def insert_silent_log(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
        cost_usd: float | None = None,
    ) -> None:
        """Insert a minimal silent-log record indicating no alert was dispatched.

        Args:
            event_id: The pipeline event identifier.
            tenant_id: Optional tenant scoping.
            cost_usd: Optional total LLM cost in USD for this pipeline run.
        """
        stmt = text(
            """
            INSERT INTO silent_log (event_id, tenant_id)
            VALUES (:event_id, :tenant_id)
            ON CONFLICT DO NOTHING
            """
        )
        await self._session.execute(
            stmt,
            {
                "event_id": event_id,
                "tenant_id": tenant_id,
            },
        )
        await self._session.flush()
