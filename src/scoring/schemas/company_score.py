"""CompanyScoreRecord domain model."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class CompanyScoreRecord:
    """A single computed score snapshot for a company + indicator pair."""
    score_id: UUID
    company_id: UUID
    indicator_id: UUID
    tenant_id: UUID
    raw_value: float | None
    score: float  # normalized [0, 100]
    percentile: float | None
    geo_adjusted: float | None
    inputs_hash: str  # SHA-256 hex of canonical JSON inputs
    computed_at: datetime

    @classmethod
    def new(
        cls,
        company_id: UUID,
        indicator_id: UUID,
        tenant_id: UUID,
        raw_value: float | None,
        score: float,
        inputs_hash: str,
        percentile: float | None = None,
        geo_adjusted: float | None = None,
    ) -> "CompanyScoreRecord":
        return cls(
            score_id=uuid4(),
            company_id=company_id,
            indicator_id=indicator_id,
            tenant_id=tenant_id,
            raw_value=raw_value,
            score=score,
            percentile=percentile,
            geo_adjusted=geo_adjusted,
            inputs_hash=inputs_hash,
            computed_at=datetime.utcnow(),
        )
