"""
IAlertFatigueRepository — protocol for reading anti-fatigue and budget state.

All methods accept tenant_id and must scope every DB query to that tenant
(REQ-N-006 multi-tenancy isolation).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing_extensions import Protocol, runtime_checkable

from src.alerts.models import BudgetState


@runtime_checkable
class IAlertFatigueRepository(Protocol):
    """Read interface for computing anti-fatigue gate inputs."""

    async def count_dispatched_today(self, user_id: UUID, tenant_id: UUID) -> int:
        """Return the number of alerts dispatched today for *user_id*.

        Only counts rows with status='dispatched'. Midnight boundary is UTC.

        Args:
            user_id: Target user.
            tenant_id: Tenant scope (included in WHERE clause).

        Returns:
            Non-negative integer count.
        """
        ...

    async def get_last_dispatch_for_ticker(
        self, user_id: UUID, ticker: str, tenant_id: UUID
    ) -> datetime | None:
        """Return the UTC timestamp of the most recent dispatched alert for *ticker*.

        Args:
            user_id: Target user.
            ticker: Stock ticker symbol (e.g. "AAPL").
            tenant_id: Tenant scope.

        Returns:
            Timezone-aware datetime, or None if no prior alert exists.
        """
        ...

    async def get_recent_event_alert_ids(
        self, event_id: UUID, user_id: UUID, tenant_id: UUID, window_minutes: int
    ) -> list[UUID]:
        """Return alert IDs generated for *event_id* within *window_minutes*.

        Used for deduplication: if any IDs are returned the event has already
        triggered an alert for this user within the window.

        Args:
            event_id: Source event UUID.
            user_id: Target user.
            tenant_id: Tenant scope.
            window_minutes: Look-back window in minutes.

        Returns:
            List of alert UUIDs (may be empty).
        """
        ...

    async def get_budget_state(self, user_id: UUID, tenant_id: UUID) -> BudgetState:
        """Return the user's budget configuration and today's spend total.

        Reads daily_budget_usd, alert_threshold_pct, and hard_stop_pct from
        user.settings JSONB.  spent_today_usd is computed from alert rows.

        Args:
            user_id: Target user.
            tenant_id: Tenant scope.

        Returns:
            BudgetState with all four fields populated.
        """
        ...

    async def get_spent_today_usd(self, user_id: UUID, tenant_id: UUID) -> float:
        """Return total cost_usd for today's dispatched alerts for *user_id*.

        Args:
            user_id: Target user.
            tenant_id: Tenant scope.

        Returns:
            Non-negative float representing USD spent since UTC midnight today.
        """
        ...
