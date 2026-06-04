"""
Pydantic v2 schemas for Layer 2 semantic memory.

Provides request (Create) and response (read) models for:
  - SemanticFactStaging  (pre-gate staging rows)
  - SemanticFact         (committed facts)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field


# ── SemanticFactStaging ───────────────────────────────────────────────────────


class SemanticFactStagingCreate(BaseModel):
    """Input schema for staging a new semantic fact."""

    entity_id: uuid.UUID
    fact_text: str
    source_invocation_id: Optional[uuid.UUID] = None


class SemanticFactStaging(BaseModel):
    """Response schema for a semantic fact staging row."""

    staging_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_id: uuid.UUID
    fact_text: str
    evidence_count: int = 1
    source_invocation_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SemanticFact ──────────────────────────────────────────────────────────────


class SemanticFactCreate(BaseModel):
    """Input schema for creating a committed semantic fact (internal use)."""

    entity_id: uuid.UUID
    fact_text: str
    embedding: list[float]
    evidence_count: int
    source_invocations: list[uuid.UUID] = Field(default_factory=list)


class SemanticFact(BaseModel):
    """Response schema for a committed semantic fact."""

    fact_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_id: uuid.UUID
    fact_text: str
    embedding: Optional[list[float]] = None
    evidence_count: int
    last_confirmed: datetime
    decayed_at: Optional[datetime] = None
    retracted_at: Optional[datetime] = None
    retracted_by: Optional[uuid.UUID] = None
    source_invocations: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def is_active(self) -> bool:
        """True when the fact has not been decayed or retracted."""
        return self.decayed_at is None and self.retracted_at is None
