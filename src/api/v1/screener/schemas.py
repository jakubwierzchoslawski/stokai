"""Pydantic schemas for the Company Screener endpoint.

All column names in ScreenerFilter.column must match SCREENER_COLUMN_WHITELIST
defined in screener_service.py.  Validation is enforced at the service layer so
that the whitelist remains a single source of truth.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ScreenerFilter(BaseModel):
    """A single filter predicate for the screener query.

    logical_op is applied between this filter and the *previous* one in the
    list.  The first filter's logical_op is ignored (it is the base predicate).
    operator "contains" uses case-insensitive LIKE (%value%).
    operator "in" expects value to be a list.
    """

    column: str
    operator: Literal["eq", "gt", "lt", "contains", "in"]
    value: Any
    logical_op: Literal["AND", "OR"] = "AND"


class ScreenerRequest(BaseModel):
    """Request body for POST /api/v1/screener.

    Sent as a POST body (not GET query params) to avoid URL-length limits
    when multiple filters are active.  This endpoint is read-only despite
    using POST — documented in the OpenAPI description.
    """

    filters: list[ScreenerFilter] = Field(default_factory=list)
    sort_column: str = "custom_score"
    sort_dir: Literal["asc", "desc"] = "desc"
    cursor: str | None = None
    page_size: int = Field(default=50, ge=1, le=200)
    event_id: UUID | None = None


class ScreenerRow(BaseModel):
    """A single company row returned by the screener."""

    company_id: UUID
    ticker: str
    name: str
    sector: str
    market_cap: float
    custom_score: float
    score_delta: float
    current_price: float  # 15-min delayed
    active_events_count: int
    active_event_categories: list[str]


class ScreenerResponse(BaseModel):
    """Cursor-paginated screener result set."""

    data: list[ScreenerRow]
    next_cursor: str | None
    total_count: int  # total matching rows (for display, not pagination)
    applied_filters: list[ScreenerFilter]
