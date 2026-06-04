"""
Unit tests for EventParser (parse_raw_event).

Pure logic tests — no I/O, no mocks required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ingestion.cold_start.event_parser import (
    GeoEventCreate,
    _cameo_to_categories,
    _clamp_intensity,
    _clamp_sentiment,
    _derive_event_id,
    parse_raw_event,
)
from src.ingestion.cold_start.types import RawHistoricalEvent

_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_raw_event(**kwargs) -> RawHistoricalEvent:
    """Build a valid RawHistoricalEvent with sensible defaults."""
    defaults = dict(
        external_id="99999",
        occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        title="Test event",
        summary="A test event summary.",
        lat=0.0,
        lon=0.0,
        geo_regions=["US"],
        cameo_code="190",
        intensity_raw=3.0,
        sentiment_raw=0.0,
        source_provider="gdelt",
        raw_payload={},
    )
    defaults.update(kwargs)
    return RawHistoricalEvent(**defaults)


@pytest.mark.unit
class TestCameoMapping:
    """Tests for CAMEO root-code → category mapping."""

    def test_cameo_190_maps_to_armed_conflict(self):
        """CAMEO code 190 → ARMED_CONFLICT."""
        result = _cameo_to_categories("190")
        assert "ARMED_CONFLICT" in result

    def test_cameo_010_maps_to_verbal_cooperation(self):
        """CAMEO code 010 → VERBAL_COOPERATION."""
        result = _cameo_to_categories("010")
        assert "VERBAL_COOPERATION" in result

    def test_cameo_19_prefix_maps_to_armed_conflict(self):
        """CAMEO codes starting with '19' → ARMED_CONFLICT."""
        result = _cameo_to_categories("195")
        assert "ARMED_CONFLICT" in result

    def test_unknown_cameo_code_maps_to_unknown(self):
        """Unknown CAMEO code → ['UNKNOWN']."""
        result = _cameo_to_categories("999")
        assert result == ["UNKNOWN"]

    def test_none_cameo_maps_to_unknown(self):
        """None cameo_code → ['UNKNOWN']."""
        result = _cameo_to_categories(None)
        assert result == ["UNKNOWN"]

    def test_empty_string_cameo_maps_to_unknown(self):
        """Empty string cameo_code → ['UNKNOWN']."""
        result = _cameo_to_categories("")
        assert result == ["UNKNOWN"]


@pytest.mark.unit
class TestIntensityClamping:
    """Tests for intensity_raw clamping to [1, 5]."""

    def test_intensity_7_clamped_to_5(self):
        """intensity_raw=7.0 is clamped to 5."""
        assert _clamp_intensity(7.0) == 5

    def test_intensity_minus2_clamped_to_1(self):
        """intensity_raw=-2.0 is clamped to 1."""
        assert _clamp_intensity(-2.0) == 1

    def test_intensity_3_unchanged(self):
        assert _clamp_intensity(3.0) == 3

    def test_intensity_1_boundary(self):
        assert _clamp_intensity(1.0) == 1

    def test_intensity_5_boundary(self):
        assert _clamp_intensity(5.0) == 5


@pytest.mark.unit
class TestSentimentClamping:
    """Tests for sentiment_raw clamping to [-1.0, 1.0]."""

    def test_sentiment_2_clamped_to_1(self):
        assert _clamp_sentiment(2.0) == pytest.approx(1.0)

    def test_sentiment_minus2_clamped_to_minus1(self):
        assert _clamp_sentiment(-2.0) == pytest.approx(-1.0)

    def test_sentiment_zero_unchanged(self):
        assert _clamp_sentiment(0.0) == pytest.approx(0.0)


@pytest.mark.unit
class TestDeterministicEventId:
    """Tests for deterministic UUID5 event_id generation."""

    def test_same_inputs_produce_same_uuid(self):
        """Same (source_provider, external_id) → same UUID across two calls."""
        uid1 = _derive_event_id("gdelt", "12345")
        uid2 = _derive_event_id("gdelt", "12345")
        assert uid1 == uid2

    def test_different_external_id_produces_different_uuid(self):
        """Different external_id → different UUID."""
        uid1 = _derive_event_id("gdelt", "12345")
        uid2 = _derive_event_id("gdelt", "99999")
        assert uid1 != uid2

    def test_different_provider_produces_different_uuid(self):
        """Different source_provider → different UUID."""
        uid1 = _derive_event_id("gdelt", "12345")
        uid2 = _derive_event_id("acled", "12345")
        assert uid1 != uid2

    def test_returns_uuid_type(self):
        result = _derive_event_id("gdelt", "abc")
        assert isinstance(result, uuid.UUID)


@pytest.mark.unit
class TestParseRawEvent:
    """Integration-level tests for parse_raw_event()."""

    def test_produces_geo_event_create(self):
        raw = _make_raw_event()
        result = parse_raw_event(raw, tenant_id=_TENANT_ID)
        assert isinstance(result, GeoEventCreate)

    def test_tenant_id_set_correctly(self):
        raw = _make_raw_event()
        result = parse_raw_event(raw, tenant_id=_TENANT_ID)
        assert result.tenant_id == _TENANT_ID

    def test_tenant_id_none_for_global_events(self):
        """Global seeded events have tenant_id=None."""
        raw = _make_raw_event()
        result = parse_raw_event(raw, tenant_id=None)
        assert result.tenant_id is None

    def test_ttl_is_none(self):
        """All seeded events carry ttl=None (infinite TTL per REQ-N-011)."""
        raw = _make_raw_event()
        result = parse_raw_event(raw)
        assert result.ttl is None

    def test_affected_sectors_defaults_to_empty(self):
        """affected_sectors must be [] — LLM classification not available at cold-start."""
        raw = _make_raw_event()
        result = parse_raw_event(raw)
        assert result.affected_sectors == []

    def test_event_id_is_deterministic_across_calls(self):
        """Same raw event parsed twice produces same event_id."""
        raw = _make_raw_event(external_id="UNIQUE_123", source_provider="gdelt")
        r1 = parse_raw_event(raw)
        r2 = parse_raw_event(raw)
        assert r1.event_id == r2.event_id

    def test_intensity_clamped_in_result(self):
        raw = _make_raw_event(intensity_raw=99.0)
        result = parse_raw_event(raw)
        assert result.intensity == 5

    def test_sentiment_clamped_in_result(self):
        raw = _make_raw_event(sentiment_raw=-50.0)
        result = parse_raw_event(raw)
        assert result.sentiment == pytest.approx(-1.0)
