"""Unit tests for WebSocket geo_modifier_update broadcast.

TDD: Tests were written before the implementation.
PLAN-F-018 TASK-004
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.scoring.schemas.geo_modifier import CompanyScoreDelta, GeoModifierPayload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload() -> GeoModifierPayload:
    return GeoModifierPayload(
        event_id=uuid4(),
        affected_companies=[
            CompanyScoreDelta(
                company_id=uuid4(),
                ticker="AAPL",
                new_geo_adjusted=72.5,
                score_delta=-7.5,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBroadcastGeoModifier:
    """Tests for broadcast_geo_modifier in the WebSocket manager."""

    @pytest.mark.asyncio
    async def test_two_subscribers_both_receive_message(self):
        """Two active subscribers both receive a geo_modifier_update message."""
        from src.api.websocket.geo_modifier_broadcaster import broadcast_geo_modifier, _connections

        payload = _make_payload()
        tenant_id = str(uuid4())

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        _connections[tenant_id] = [ws1, ws2]

        try:
            await broadcast_geo_modifier(payload, tenant_id)
        finally:
            _connections.pop(tenant_id, None)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

        sent_msg = ws1.send_json.call_args[0][0]
        assert sent_msg["type"] == "geo_modifier_update"

    @pytest.mark.asyncio
    async def test_disconnected_subscriber_removed_other_still_receives(self):
        """One subscriber raising disconnect is removed; the other still receives."""
        from src.api.websocket.geo_modifier_broadcaster import broadcast_geo_modifier, _connections
        from fastapi.websockets import WebSocketDisconnect

        payload = _make_payload()
        tenant_id = str(uuid4())

        ws_dead = AsyncMock()
        ws_dead.send_json.side_effect = WebSocketDisconnect()

        ws_alive = AsyncMock()
        _connections[tenant_id] = [ws_dead, ws_alive]

        try:
            await broadcast_geo_modifier(payload, tenant_id)
        finally:
            pass

        # Dead connection removed; alive connection received message
        assert ws_dead not in _connections.get(tenant_id, [])
        ws_alive.send_json.assert_called_once()

        _connections.pop(tenant_id, None)

    @pytest.mark.asyncio
    async def test_zero_subscribers_completes_without_error(self):
        """With zero subscribers, broadcast completes immediately without error."""
        from src.api.websocket.geo_modifier_broadcaster import broadcast_geo_modifier, _connections

        payload = _make_payload()
        tenant_id = str(uuid4())

        # Ensure no connections for this tenant
        _connections.pop(tenant_id, None)

        # Should not raise
        await broadcast_geo_modifier(payload, tenant_id)

    @pytest.mark.asyncio
    async def test_payload_serialization_matches_model_dump(self):
        """The payload in the sent message matches GeoModifierPayload.model_dump(mode='json')."""
        from src.api.websocket.geo_modifier_broadcaster import broadcast_geo_modifier, _connections

        payload = _make_payload()
        tenant_id = str(uuid4())

        ws = AsyncMock()
        _connections[tenant_id] = [ws]

        try:
            await broadcast_geo_modifier(payload, tenant_id)
        finally:
            _connections.pop(tenant_id, None)

        ws.send_json.assert_called_once()
        sent_msg = ws.send_json.call_args[0][0]

        assert sent_msg["type"] == "geo_modifier_update"
        assert sent_msg["payload"] == payload.model_dump(mode="json")
