"""
api.websocket.workflow_notifier — WebSocket push for workflow completion events.

WorkflowNotifier pushes a status update to connected clients when a workflow
run completes (COMPLETED, HIL_PENDING, BLOCKED, TIMEOUT, FAILED).

No-op if the client has disconnected or the WebSocket manager is not initialised.

PLAN-F-007 TASK-008
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── In-process connection registry ───────────────────────────────────────────

# Maps tenant_id → list of active WebSocket connections for that tenant.
# In a multi-process deployment this should be replaced with Redis pub/sub.
_connections: dict[str, list[Any]] = {}


def register_connection(tenant_id: str, websocket: Any) -> None:
    """Register a WebSocket connection for a tenant.

    Args:
        tenant_id: The tenant to which this connection belongs.
        websocket: A FastAPI WebSocket instance.
    """
    if tenant_id not in _connections:
        _connections[tenant_id] = []
    _connections[tenant_id].append(websocket)
    logger.debug("WebSocket registered for tenant=%s (total=%d)", tenant_id, len(_connections[tenant_id]))


def deregister_connection(tenant_id: str, websocket: Any) -> None:
    """Remove a WebSocket connection for a tenant.

    Args:
        tenant_id: The tenant identifier.
        websocket: The WebSocket instance to remove.
    """
    if tenant_id in _connections:
        try:
            _connections[tenant_id].remove(websocket)
        except ValueError:
            pass


async def push_workflow_update(
    workflow_id: str,
    status: str,
    tenant_id: str,
) -> None:
    """Push a workflow status update to all connections for a tenant.

    No-op if there are no active connections for this tenant.

    Args:
        workflow_id: UUID string of the workflow run.
        status: Final status string (e.g. "COMPLETED", "FAILED").
        tenant_id: Tenant identifier for routing.
    """
    connections = list(_connections.get(tenant_id, []))
    if not connections:
        logger.debug(
            "push_workflow_update: no active connections for tenant=%s", tenant_id
        )
        return

    payload = {
        "type": "workflow_update",
        "workflow_id": workflow_id,
        "status": status,
    }

    dead: list[Any] = []
    for ws in connections:
        try:
            await ws.send_json(payload)
        except Exception:
            # Client disconnected or send failed — mark for removal
            dead.append(ws)

    for ws in dead:
        deregister_connection(tenant_id, ws)
