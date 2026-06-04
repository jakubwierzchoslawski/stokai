"""
tests.security.test_idor_prevention — IDOR prevention tests.

Covers AC-002: cross-tenant URL access returns HTTP 403 or 404.

Tests verify_resource_ownership and resource_owner_dependency utilities.
"""
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.security.ownership import (
    ResourceNotOwnedError,
    resource_owner_dependency,
    verify_resource_ownership,
)


# ── Minimal stub resource ─────────────────────────────────────────────────────

class _StubResource:
    """Mimics an ORM model with a tenant_id attribute."""

    def __init__(self, tenant_id: Optional[uuid.UUID] = None) -> None:
        self.tenant_id = tenant_id
        self.id = uuid.uuid4()


# ── verify_resource_ownership unit tests ─────────────────────────────────────

def test_verify_resource_ownership_passes_for_matching_tenant() -> None:
    """Should return None (no exception) when tenant_ids match."""
    tenant_id = uuid.uuid4()
    resource = _StubResource(tenant_id=tenant_id)
    # Must not raise
    result = verify_resource_ownership(resource, tenant_id, resource.id)
    assert result is None


def test_verify_resource_ownership_raises_for_mismatched_tenant() -> None:
    """Should raise ResourceNotOwnedError when tenant_ids differ."""
    owner_tenant = uuid.uuid4()
    requester_tenant = uuid.uuid4()
    resource = _StubResource(tenant_id=owner_tenant)

    with pytest.raises(ResourceNotOwnedError):
        verify_resource_ownership(resource, requester_tenant, resource.id)


def test_verify_resource_ownership_raises_for_none_resource_tenant() -> None:
    """Should raise ResourceNotOwnedError when resource.tenant_id is None."""
    resource = _StubResource(tenant_id=None)

    with pytest.raises(ResourceNotOwnedError):
        verify_resource_ownership(resource, uuid.uuid4(), resource.id)


# ── resource_owner_dependency tests ──────────────────────────────────────────

def _make_app_with_dependency(
    fetched_resource: Any,
    current_user_tenant_id: uuid.UUID,
) -> FastAPI:
    """Build a minimal FastAPI app with a protected endpoint."""
    from fastapi import Depends

    app = FastAPI()

    async def _fetch_fn(resource_id: uuid.UUID, tenant_id: uuid.UUID) -> Any:
        return fetched_resource

    owner_dep = resource_owner_dependency(_fetch_fn)

    # Mock get_current_user so we don't need a real DB
    mock_user = MagicMock()
    mock_user.tenant_id = current_user_tenant_id

    async def _mock_get_current_user():
        return mock_user

    # Override the dependency
    from src.api.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    @app.get("/items/{resource_id}")
    async def get_item(resource=Depends(owner_dep)):
        return {"id": str(resource.id)}

    return app


def test_resource_owner_dependency_returns_resource_when_owned() -> None:
    """Should return the resource when tenant_id matches."""
    tenant_id = uuid.uuid4()
    resource = _StubResource(tenant_id=tenant_id)
    app = _make_app_with_dependency(resource, tenant_id)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/items/{resource.id}")
    assert response.status_code == 200


def test_resource_owner_dependency_raises_404_when_resource_not_found() -> None:
    """Should return 404 when get_resource_fn returns None."""
    tenant_id = uuid.uuid4()
    app = _make_app_with_dependency(None, tenant_id)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/items/{uuid.uuid4()}")
    assert response.status_code == 404


def test_resource_owner_dependency_raises_404_when_tenant_mismatch() -> None:
    """Should return 404 (not 403) when tenant_ids don't match."""
    owner_tenant = uuid.uuid4()
    requester_tenant = uuid.uuid4()
    resource = _StubResource(tenant_id=owner_tenant)
    app = _make_app_with_dependency(resource, requester_tenant)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/items/{resource.id}")
    assert response.status_code == 404


def test_cross_tenant_url_access_returns_404() -> None:
    """Integration: tenant_B accessing tenant_A's resource returns 404.

    This test creates a resource owned by tenant_A, then tries to access it
    as tenant_B — the endpoint must return 404, not 403 or 200.
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Resource owned by tenant_A
    resource = _StubResource(tenant_id=tenant_a)

    # App configured with tenant_B as the current user
    app = _make_app_with_dependency(resource, tenant_b)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/items/{resource.id}")
    assert response.status_code == 404
    # Ensure no sensitive information leaks in the error body
    body = response.json()
    assert "tenant" not in str(body).lower() or "NOT_FOUND" in str(body)
