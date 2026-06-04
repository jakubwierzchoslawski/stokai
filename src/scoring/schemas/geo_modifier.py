"""Geo-modifier WebSocket DTO schemas.

GeoModifierPayload is broadcast to subscribed map clients after a geo-modifier
task completes. CompanyScoreDelta carries per-company score change info.

PLAN-F-018 TASK-001
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class CompanyScoreDelta(BaseModel):
    """Per-company score change delivered in a GeoModifierPayload."""

    company_id: UUID
    ticker: str
    new_geo_adjusted: float
    score_delta: float  # new_geo_adjusted - previous_geo_adjusted


class GeoModifierPayload(BaseModel):
    """WebSocket message payload for geo_modifier_update broadcasts."""

    event_id: UUID
    affected_companies: list[CompanyScoreDelta]
