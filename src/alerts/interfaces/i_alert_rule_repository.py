"""
IAlertRuleRepository — protocol for fetching active alert rules per tenant.
"""
from __future__ import annotations

from uuid import UUID

from typing_extensions import Protocol, runtime_checkable

from src.alerts.models import AlertRuleRow


@runtime_checkable
class IAlertRuleRepository(Protocol):
    """Read interface for the alert_rule table.

    All queries are scoped to a single tenant_id.  Implementations must include
    tenant_id in every WHERE clause (REQ-N-006).
    """

    async def get_active_rules(self, tenant_id: UUID) -> list[AlertRuleRow]:
        """Return all enabled alert rules for *tenant_id*.

        Args:
            tenant_id: Tenant whose rules to load.

        Returns:
            List of AlertRuleRow, each joined with the owning user's email.
            Returns an empty list when no rules exist.
        """
        ...
