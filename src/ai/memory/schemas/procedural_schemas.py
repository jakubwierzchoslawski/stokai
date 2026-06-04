"""
Pydantic v2 schemas for Layer 3 procedural memory.

Provides request (Create) and response models for procedural_pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class AuthoredBy(StrEnum):
    HUMAN = "human"
    MINED = "mined"


# ── ProceduralPattern ─────────────────────────────────────────────────────────


class ProceduralPatternCreate(BaseModel):
    """Input schema for creating a new procedural pattern."""

    pattern_type: str
    context_tags: list[str] = Field(default_factory=list)
    pattern_text: str
    authored_by: AuthoredBy = AuthoredBy.HUMAN
    version: int = 1
    success_rate: Optional[float] = None
    sample_size: Optional[int] = None
    confidence: Optional[float] = None
    recommended_for_agents: list[str] = Field(default_factory=list)


class ProceduralPattern(BaseModel):
    """Response schema for a procedural pattern."""

    pattern_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    pattern_type: str
    context_tags: list[str] = Field(default_factory=list)
    pattern_text: str
    authored_by: str
    approved_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    version: int = 1
    success_rate: Optional[float] = None
    sample_size: Optional[int] = None
    confidence: Optional[float] = None
    recommended_for_agents: list[str] = Field(default_factory=list)
    created_at: datetime
    retracted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def is_active(self) -> bool:
        """Return True when approved and not retracted."""
        return self.approved_at is not None and self.retracted_at is None
