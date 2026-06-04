"""
ai.workflows.on_demand.node_context — NodeContext dataclass.

NodeContext is constructed once at graph-build time and injected into every
DeterministicNode via partial application.  Nodes must not construct their own
database sessions or repository instances (DIP).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ICompanyRepository(Protocol):
    """Minimal protocol for looking up company state."""

    async def get_company_state(
        self, company_id: Any, tenant_id: Any
    ) -> dict | None:
        """Return company fundamentals dict or None if not found."""
        ...


@runtime_checkable
class IGeoEventRepository(Protocol):
    """Minimal protocol for querying geo events linked to a company."""

    async def get_active_events_for_company(
        self, company_id: Any, tenant_id: Any, days: int = 30, limit: int = 50
    ) -> list[dict]:
        """Return up to `limit` active geo events for the company in the last `days`."""
        ...


@dataclass
class NodeContext:
    """Container for all dependencies injected into on-demand workflow nodes.

    Constructed once at graph build time via a factory function.  Individual
    nodes receive the full context and extract only the repositories they need.
    """

    company_repo: ICompanyRepository
    geo_event_repo: IGeoEventRepository
    extra: dict = field(default_factory=dict)
