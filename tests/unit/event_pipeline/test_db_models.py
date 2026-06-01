"""Unit tests for RawEvent and EventRecord DB models (TASK-002).

TDD: tests written before model implementation.
Integration tests requiring a live DB are marked @pytest.mark.integration.
Unit tests here validate model attributes and constraints at the Python layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


class TestRawEventModelStructure:
    """Validate RawEvent column definitions without a DB connection."""

    def test_raw_event_has_required_columns(self):
        """RawEvent ORM model exposes all required columns."""
        from src.db.models.raw_event import RawEvent
        from sqlalchemy import inspect

        mapper = inspect(RawEvent)
        col_names = {c.key for c in mapper.columns}

        required = {
            "event_id", "tenant_id", "source", "raw_payload",
            "detected_at", "pipeline_status", "failed_step",
            "error_detail", "fingerprint", "created_at",
        }
        assert required.issubset(col_names), (
            f"Missing columns: {required - col_names}"
        )

    def test_raw_event_pipeline_status_has_default(self):
        """pipeline_status column defaults to 'pending'."""
        from src.db.models.raw_event import RawEvent

        event = RawEvent(
            event_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            source="GDELT",
        )
        assert event.pipeline_status == "pending"

    def test_raw_event_valid_statuses(self):
        """All five valid pipeline_status values can be assigned."""
        from src.db.models.raw_event import RawEvent, VALID_PIPELINE_STATUSES

        for status in ("pending", "running", "completed", "failed", "duplicate"):
            assert status in VALID_PIPELINE_STATUSES


class TestEventRecordModelStructure:
    """Validate EventRecord (geopolitical_events extension) column definitions."""

    def test_event_record_has_required_columns(self):
        """EventRecord ORM model exposes all required columns."""
        from src.db.models.event_record import EventRecord
        from sqlalchemy import inspect

        mapper = inspect(EventRecord)
        col_names = {c.key for c in mapper.columns}

        required = {
            "event_id", "tenant_id", "source", "detected_at",
            "category", "intensity", "geo_lat", "geo_lon",
            "raw_payload", "raw_event_id", "generated_at",
        }
        assert required.issubset(col_names), (
            f"Missing columns: {required - col_names}"
        )

    def test_event_record_table_name(self):
        """EventRecord maps to the geopolitical_events table."""
        from src.db.models.event_record import EventRecord

        assert EventRecord.__tablename__ == "geopolitical_events"


class TestRawEventModelsExported:
    """Validate that models are exported from db.models package."""

    def test_raw_event_importable_from_db_models(self):
        """RawEvent can be imported from src.db.models."""
        from src.db.models import RawEvent
        assert RawEvent is not None

    def test_event_record_importable_from_db_models(self):
        """EventRecord can be imported from src.db.models."""
        from src.db.models import EventRecord
        assert EventRecord is not None
