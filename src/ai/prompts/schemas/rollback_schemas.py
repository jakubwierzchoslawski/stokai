"""src.ai.prompts.schemas.rollback_schemas — Pydantic models for rollback operations.

PLAN-F-014 TASK-004 (AC-003).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RollbackRequest(BaseModel):
    """Request payload for a prompt rollback operation."""

    role_id: str = Field(description="Prompt role identifier.")
    to_version: str = Field(
        description="Target version SHA to roll back to.",
        min_length=40,
        max_length=40,
    )
    published_by: str = Field(
        default="cli",
        description="Actor triggering the rollback: 'cli' | 'admin'.",
    )


class RollbackResult(BaseModel):
    """Result of a prompt rollback operation.

    The effective_at timestamp must be within 60 seconds of the rollback request
    to satisfy AC-003 SLA.
    """

    role_id: str = Field(description="Prompt role identifier.")
    previous_version: str = Field(
        description="Version SHA that held the 'production' label before the rollback.",
    )
    rolled_back_to: str = Field(
        description="Version SHA that now holds the 'production' label.",
    )
    effective_at: datetime = Field(
        description="UTC timestamp when the rollback took effect. Must be < 60 s after request.",
    )
