"""
Pydantic v2 schemas for golden_dataset_item.

Provides Create, response, and candidate schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GoldenDatasetItemCreate(BaseModel):
    """Input schema for creating a new golden dataset item (always inactive)."""

    input: dict[str, Any]
    expected_output: dict[str, Any]
    quality_metrics: dict[str, Any]
    source: Literal["hand_authored", "admin_override"]


class GoldenDatasetItem(BaseModel):
    """Response schema for a golden dataset item row."""

    item_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    input: dict[str, Any]
    expected_output: dict[str, Any]
    quality_metrics: dict[str, Any]
    source: str
    active: bool
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @property
    def is_active(self) -> bool:
        """True when the item is in the active regression suite."""
        return self.active is True

    @property
    def is_candidate(self) -> bool:
        """True when the item is awaiting approval."""
        return self.active is False and self.approved_at is None


class GoldenDatasetCandidate(GoldenDatasetItem):
    """Schema for golden dataset items pending human approval."""
    pass
