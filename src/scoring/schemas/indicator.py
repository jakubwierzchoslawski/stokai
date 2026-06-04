"""Indicator domain models (dataclasses/Pydantic-free domain objects)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class IndicatorRecord:
    """Current (latest) state of an indicator."""
    indicator_id: UUID
    tenant_id: UUID
    name: str
    formula_dsl: str
    normalization_mode: str  # "percentile" | "z_score" | "min_max"
    normalization_config: dict[str, Any]  # min_val, max_val etc.
    direction: str  # "higher_better" | "lower_better"
    geo_weight: float  # [0.0, 1.0]
    version: int  # current version number
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    @classmethod
    def new(
        cls,
        tenant_id: UUID,
        name: str,
        formula_dsl: str,
        normalization_mode: str = "percentile",
        normalization_config: dict[str, Any] | None = None,
        direction: str = "higher_better",
        geo_weight: float = 0.0,
    ) -> "IndicatorRecord":
        now = datetime.utcnow()
        return cls(
            indicator_id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            formula_dsl=formula_dsl,
            normalization_mode=normalization_mode,
            normalization_config=normalization_config or {},
            direction=direction,
            geo_weight=geo_weight,
            version=1,
            created_at=now,
            updated_at=now,
        )


@dataclass
class IndicatorVersionRecord:
    """Historical version snapshot of an indicator's DSL."""
    version_id: UUID
    indicator_id: UUID
    tenant_id: UUID
    version: int
    formula_dsl: str
    diff_tokens: list[str]  # token-level diff vs. previous version
    created_at: datetime

    @classmethod
    def from_indicator(
        cls,
        indicator: IndicatorRecord,
        diff_tokens: list[str] | None = None,
    ) -> "IndicatorVersionRecord":
        return cls(
            version_id=uuid4(),
            indicator_id=indicator.indicator_id,
            tenant_id=indicator.tenant_id,
            version=indicator.version,
            formula_dsl=indicator.formula_dsl,
            diff_tokens=diff_tokens or [],
            created_at=datetime.utcnow(),
        )
