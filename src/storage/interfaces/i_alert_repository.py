"""
IAlertRepository — protocol for alert and silent-log table persistence.
"""
from __future__ import annotations

from uuid import UUID

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class IAlertRepository(Protocol):
    """Repository interface for the alert table and silent-log records."""

    async def insert_alert(
        self, alert_data: dict, cost_usd: float | None = None
    ) -> UUID:
        """Insert an alert row and return the generated alert_id.

        Args:
            alert_data: Dictionary of column-value pairs for the alert row.
                Expected keys: tenant_id, event_id, company_id, rule_id,
                channel, sent_at, content, confidence.
            cost_usd: Optional total LLM cost in USD for this pipeline run.
                Written to the ``cost_usd`` column. NULL when not provided.

        Returns:
            UUID of the newly inserted alert row.
        """
        ...

    async def insert_silent_log(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
        cost_usd: float | None = None,
    ) -> None:
        """Insert a minimal silent-log record indicating no alert was dispatched.

        Args:
            event_id: The event that was processed without triggering an alert.
            tenant_id: Owning tenant, or None for global events.
            cost_usd: Optional total LLM cost in USD for this pipeline run.
        """
        ...
