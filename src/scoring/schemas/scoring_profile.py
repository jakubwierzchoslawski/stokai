"""ScoringProfile domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class ProfileIndicatorWeight:
    """Indicator + weight pair within a scoring profile."""
    indicator_id: UUID
    weight: float  # relative weight; normalized to sum=1.0 at compute time


@dataclass
class ScoringProfileRecord:
    """A scoring profile aggregating multiple indicator scores with weights."""
    profile_id: UUID
    tenant_id: UUID
    name: str
    indicators: list[ProfileIndicatorWeight]
    is_builtin: bool
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(
        cls,
        tenant_id: UUID,
        name: str,
        indicators: list[ProfileIndicatorWeight],
        is_builtin: bool = False,
    ) -> "ScoringProfileRecord":
        now = datetime.utcnow()
        return cls(
            profile_id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            indicators=indicators,
            is_builtin=is_builtin,
            version=1,
            created_at=now,
            updated_at=now,
        )
