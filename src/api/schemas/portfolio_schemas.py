"""
api.schemas.portfolio_schemas — Pydantic request/response DTOs for portfolio and watchlist APIs.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Portfolio schemas ──────────────────────────────────────────────────────────


class CreatePortfolioRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PortfolioDTO(BaseModel):
    portfolio_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Position schemas ───────────────────────────────────────────────────────────


class AddPositionRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    shares: float = Field(..., gt=0)
    cost_basis: float | None = Field(default=None, gt=0)
    source: str = Field(default="manual", pattern=r"^(manual|csv|broker)$")


class PositionDTO(BaseModel):
    position_id: uuid.UUID
    portfolio_id: uuid.UUID
    company_id: uuid.UUID
    ticker: str
    shares: float
    cost_basis: float | None
    added_at: datetime
    source: str

    class Config:
        from_attributes = True


# ── Watchlist schemas ──────────────────────────────────────────────────────────


class AddWatchlistRequest(BaseModel):
    company_id: uuid.UUID
    ticker: str = Field(..., min_length=1, max_length=20)


class WatchlistItemDTO(BaseModel):
    item_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    ticker: str
    added_at: datetime

    class Config:
        from_attributes = True
