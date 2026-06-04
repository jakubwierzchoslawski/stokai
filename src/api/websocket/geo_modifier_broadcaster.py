"""
api.websocket.geo_modifier_broadcaster — WebSocket push for geo-modifier score updates.

Broadcasts GeoModifierPayload to all subscribed map clients for a given tenant.
Uses asyncio.gather for fan-out. Disconnected clients are silently removed.

PLAN-F-018 TASK-004
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.scoring.schemas.geo_modifier import GeoModifierPayload

logger = logging.getLogger(__name__)

# ── In-process connection registry ───────────────────────────────────────────

# Maps tenant_id → list of active WebSocket connections for that tenant.
# In a multi-process deployment this should be replaced with Redis pub/sub.
_connections: dict[str, list[Any]] = {}


def register_geo_connection(tenant_id: str, websocket: Any) -> None:
    """Register a WebSocket connection for geo-modifier broadcasts.

    Args:
        tenant_id: The tenant to which this connection belongs.
        websocket: A FastAPI WebSocket instance.
    """
    if tenant_id not in _connections:
        _connections[tenant_id] = []
    _connections[tenant_id].append(websocket)
    logger.debug(
        "geo_modifier: WebSocket registered for tenant=%s (total=%d)",
        tenant_id,
        len(_connections[tenant_id]),
    )


def deregister_geo_connection(tenant_id: str, websocket: Any) -> None:
    """Remove a WebSocket connection from geo-modifier broadcast registry.

    Args:
        tenant_id: The tenant identifier.
        websocket: The WebSocket instance to remove.
    """
    if tenant_id in _connections:
        try:
            _connections[tenant_id].remove(websocket)
        except ValueError:
            pass


async def broadcast_geo_modifier(
    payload: GeoModifierPayload,
    tenant_id: str,
) -> None:
    """Broadcast a GeoModifierPayload to all subscribed map clients for a tenant.

    Uses asyncio.gather for concurrent fan-out. Catches WebSocketDisconnect
    and other send errors per connection — one bad connection never blocks the rest.
    Disconnected connections are removed from the registry.

    Args:
        payload: The geo-modifier payload to broadcast.
        tenant_id: Tenant identifier to scope the broadcast.
    """
    connections = list(_connections.get(tenant_id, []))
    if not connections:
        logger.debug(
            "broadcast_geo_modifier: no active connections for tenant=%s", tenant_id
        )
        return

    message = {
        "type": "geo_modifier_update",
        "payload": payload.model_dump(mode="json"),
    }

    dead: list[Any] = []

    async def _send(ws: Any) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)

    await asyncio.gather(*(_send(ws) for ws in connections), return_exceptions=True)

    for ws in dead:
        deregister_geo_connection(tenant_id, ws)
        logger.debug(
            "broadcast_geo_modifier: removed disconnected WebSocket for tenant=%s",
            tenant_id,
        )
