"""
Unit tests for the admin data-source management FastAPI router (TASK-006).

All external collaborators (AdminSourceService, require_admin, DB session) are
mocked so no real database or Redis instance is needed.

Tests cover:
  - GET /admin/sources returns 200 with list of sources + health stats.
  - POST /admin/sources returns 201 with new source (enabled=False).
  - GET /admin/sources/{id} returns 200 with source + health stats.
  - GET /admin/sources/{id} returns 404 for unknown source.
  - PATCH /admin/sources/{id}/enable returns 200 after toggling enabled flag.
  - GET /admin/sources/{id}/health returns 200 with health stats.
  - PUT /admin/bindings returns 200 after upsert.
  - DELETE /admin/bindings returns 204.
  - Non-admin user receives 403 on any endpoint.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.router import admin_router
from src.admin.dependencies import get_admin_source_service, require_admin
from src.admin.health.counter import HealthStats
from src.admin.schemas import (
    BindingResponse,
    HealthStatsResponse,
    SourceConfigResponse,
)
from src.storage.models.market_source_binding import MarketSourceBinding
from src.storage.models.source_config import SourceConfig
from src.storage.models.user import User, UserRole


# ── App setup ─────────────────────────────────────────────────────────────────

def _build_app(service: "MagicMock", user: "MagicMock | None" = None) -> FastAPI:
    """Build a minimal FastAPI app with admin_router and mocked dependencies."""
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1")

    mock_user = user or _make_admin_user()

    app.dependency_overrides[require_admin] = lambda: mock_user
    app.dependency_overrides[get_admin_source_service] = lambda: service
    return app


def _make_admin_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.role = UserRole.admin
    return user


def _make_end_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.role = UserRole.end_user
    return user


def _make_source(enabled: bool = False) -> MagicMock:
    src = MagicMock(spec=SourceConfig)
    src.source_id = uuid.uuid4()
    src.interface_type = "PriceProvider"
    src.display_name = "Finnhub"
    src.enabled = enabled
    src.config = {}
    src.cost_tier = "low"
    src.priority = 1
    src.updated_at = None
    return src


def _make_health() -> HealthStats:
    return HealthStats(
        source_id="src-001",
        calls_today=10,
        errors_today=1,
        rate_limit_pct_used=5.0,
        estimated_cost_today=0.001,
    )


def _make_binding() -> MagicMock:
    b = MagicMock(spec=MarketSourceBinding)
    b.market_id = uuid.uuid4()
    b.interface_type = "PriceProvider"
    b.source_id = uuid.uuid4()
    b.role = "primary"
    return b


# ── GET /admin/sources ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_list_sources_returns_200_with_sources() -> None:
    source = _make_source()
    health = _make_health()

    service = MagicMock()
    service.list_sources = AsyncMock(return_value=[source])
    service.get_source_health = AsyncMock(return_value=health)

    client = TestClient(_build_app(service))
    resp = client.get("/api/v1/admin/sources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["display_name"] == "Finnhub"
    assert "credentials_ref" not in item


# ── POST /admin/sources ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_create_source_returns_201() -> None:
    created = _make_source(enabled=False)

    service = MagicMock()
    service.create_source = AsyncMock(return_value=created)

    client = TestClient(_build_app(service))
    payload = {
        "display_name": "Finnhub",
        "interface_type": "PriceProvider",
        "credentials_ref": "env:FINNHUB_API_KEY",
        "config": {},
        "cost_tier": "low",
        "priority": 1,
    }
    resp = client.post("/api/v1/admin/sources", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["enabled"] is False
    assert "credentials_ref" not in data


# ── GET /admin/sources/{source_id} ────────────────────────────────────────────

@pytest.mark.unit
def test_get_source_returns_200_with_health() -> None:
    source = _make_source()
    health = _make_health()

    service = MagicMock()
    service.get_source = AsyncMock(return_value=source)
    service.get_source_health = AsyncMock(return_value=health)

    client = TestClient(_build_app(service))
    resp = client.get(f"/api/v1/admin/sources/{source.source_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["display_name"] == "Finnhub"
    assert "credentials_ref" not in body["data"]


@pytest.mark.unit
def test_get_source_returns_404_for_unknown_id() -> None:
    service = MagicMock()
    service.get_source = AsyncMock(return_value=None)

    client = TestClient(_build_app(service))
    resp = client.get(f"/api/v1/admin/sources/{uuid.uuid4()}")

    assert resp.status_code == 404
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == "NOT_FOUND"


# ── PATCH /admin/sources/{source_id}/enable ───────────────────────────────────

@pytest.mark.unit
def test_toggle_enable_returns_200() -> None:
    updated = _make_source(enabled=True)

    service = MagicMock()
    service.set_enabled = AsyncMock(return_value=updated)

    client = TestClient(_build_app(service))
    resp = client.patch(
        f"/api/v1/admin/sources/{updated.source_id}/enable",
        json={"enabled": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["enabled"] is True


# ── GET /admin/sources/{source_id}/health ────────────────────────────────────

@pytest.mark.unit
def test_get_source_health_returns_200() -> None:
    source = _make_source()
    health = _make_health()

    service = MagicMock()
    service.get_source = AsyncMock(return_value=source)
    service.get_source_health = AsyncMock(return_value=health)

    client = TestClient(_build_app(service))
    resp = client.get(f"/api/v1/admin/sources/{source.source_id}/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["calls_today"] == 10
    assert body["data"]["errors_today"] == 1


# ── PUT /admin/bindings ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_upsert_binding_returns_200() -> None:
    binding = _make_binding()

    service = MagicMock()
    service.upsert_binding = AsyncMock(return_value=binding)

    client = TestClient(_build_app(service))
    payload = {
        "market_id": str(binding.market_id),
        "interface_type": "PriceProvider",
        "source_id": str(binding.source_id),
        "role": "primary",
    }
    resp = client.put("/api/v1/admin/bindings", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["role"] == "primary"


# ── DELETE /admin/bindings ────────────────────────────────────────────────────

@pytest.mark.unit
def test_delete_binding_returns_204() -> None:
    service = MagicMock()
    service.delete_binding = AsyncMock(return_value=None)

    binding = _make_binding()
    client = TestClient(_build_app(service))
    payload = {
        "market_id": str(binding.market_id),
        "interface_type": "PriceProvider",
        "source_id": str(binding.source_id),
    }
    resp = client.request("DELETE", "/api/v1/admin/bindings", json=payload)

    assert resp.status_code == 204


# ── Non-admin access control ──────────────────────────────────────────────────

@pytest.mark.unit
def test_non_admin_receives_403() -> None:
    """A non-admin user attempting GET /admin/sources must receive HTTP 403."""
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1")

    # Override require_admin to raise 403 (simulating an end user)
    from fastapi import HTTPException, status

    def _deny():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )

    service = MagicMock()
    app.dependency_overrides[require_admin] = _deny
    app.dependency_overrides[get_admin_source_service] = lambda: service

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/admin/sources")
    assert resp.status_code == 403
