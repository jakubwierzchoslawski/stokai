"""
admin.schemas — Pydantic request/response models for the admin data-source
management API (PLAN-F-028).

Security note: credentials_ref is WRITE-ONLY. It appears in request bodies
(SourceConfigCreate) but is excluded from all response models via
``model_config = ConfigDict(... exclude={"credentials_ref"})`` on the
response schema. This prevents accidental leakage of vault-reference strings
in GET responses (even though they are references, not secrets).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CREDENTIALS_REF_RE = re.compile(r"^(env|vault):[A-Z0-9_]+$")


# ── Request models ─────────────────────────────────────────────────────────────

class SourceConfigCreate(BaseModel):
    """Request body for POST /api/v1/admin/sources."""

    display_name: str = Field(..., max_length=120)
    interface_type: str = Field(
        ...,
        description=(
            "Provider interface tag. One of: PriceProvider, FundamentalsProvider, "
            "NewsProvider, FilingsProvider, MacroProvider, SocialProvider."
        ),
    )
    credentials_ref: str = Field(
        ...,
        description="Vault-reference string, e.g. env:MY_API_KEY",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    cost_tier: str = Field(..., description="free | low | medium | high")
    priority: int = Field(default=0, ge=0)

    @field_validator("credentials_ref")
    @classmethod
    def validate_credentials_ref(cls, v: str) -> str:
        if not _CREDENTIALS_REF_RE.match(v):
            raise ValueError(
                "credentials_ref must match ^(env|vault):[A-Z0-9_]+$ "
                "(e.g. env:MY_API_KEY). Raw API keys are not accepted."
            )
        return v

    @field_validator("cost_tier")
    @classmethod
    def validate_cost_tier(cls, v: str) -> str:
        allowed = {"free", "low", "medium", "high"}
        if v not in allowed:
            raise ValueError(f"cost_tier must be one of {allowed}, got {v!r}")
        return v


class SourceConfigUpdate(BaseModel):
    """Request body for PATCH /api/v1/admin/sources/{source_id} (partial update)."""

    display_name: str | None = Field(None, max_length=120)
    interface_type: str | None = None
    credentials_ref: str | None = None
    config: dict[str, Any] | None = None
    cost_tier: str | None = None
    priority: int | None = None

    @field_validator("credentials_ref")
    @classmethod
    def validate_credentials_ref(cls, v: str | None) -> str | None:
        if v is not None and not _CREDENTIALS_REF_RE.match(v):
            raise ValueError(
                "credentials_ref must match ^(env|vault):[A-Z0-9_]+$"
            )
        return v

    @field_validator("cost_tier")
    @classmethod
    def validate_cost_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in {"free", "low", "medium", "high"}:
            raise ValueError("cost_tier must be one of free | low | medium | high")
        return v


class EnableToggleRequest(BaseModel):
    """Request body for PATCH /api/v1/admin/sources/{source_id}/enable."""

    enabled: bool


class BindingUpsertRequest(BaseModel):
    """Request body for PUT /api/v1/admin/bindings."""

    market_id: uuid.UUID
    interface_type: str
    source_id: uuid.UUID
    role: str = Field(..., pattern="^(primary|fallback)$")


class BindingDeleteRequest(BaseModel):
    """Request body for DELETE /api/v1/admin/bindings."""

    market_id: uuid.UUID
    interface_type: str
    source_id: uuid.UUID


# ── Response models ────────────────────────────────────────────────────────────

class HealthStatsResponse(BaseModel):
    """Embedded health statistics in SourceConfigResponse."""

    calls_today: int = 0
    errors_today: int = 0
    rate_limit_pct_used: float = 0.0
    estimated_cost_today: float = 0.0


class SourceConfigResponse(BaseModel):
    """Response schema for source_config rows.

    credentials_ref is deliberately excluded (write-only — never returned).
    """

    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID
    interface_type: str
    display_name: str
    enabled: bool
    config: dict[str, Any]
    cost_tier: str
    priority: int
    health: HealthStatsResponse | None = None

    # credentials_ref is NOT included here — it is write-only.


class BindingResponse(BaseModel):
    """Response schema for market_source_binding rows."""

    model_config = ConfigDict(from_attributes=True)

    market_id: uuid.UUID
    interface_type: str
    source_id: uuid.UUID
    role: str
