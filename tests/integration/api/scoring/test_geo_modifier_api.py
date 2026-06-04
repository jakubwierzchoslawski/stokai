"""Integration tests for POST /api/v1/scoring/geo-modifier/reapply endpoint.

TDD: Tests were written before the implementation.
PLAN-F-018 TASK-007
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.integration

TENANT_ID = uuid4()

# JWT is decoded via src.api.auth_deps._decode_token which calls get_settings()
_SETTINGS_PATCH = "src.api.auth_deps.get_settings"
_ENQUEUE_PATCH = "src.api.v1.scoring.geo_modifier._enqueue_geo_modifier"


def _make_jwt_token(role: str = "end_user", tenant_id: UUID | None = None):
    """Create a signed JWT token using the test-secret key."""
    from jose import jwt
    from datetime import datetime, timedelta, timezone

    payload = {
        "sub": str(uuid4()),
        "tenant_id": str(tenant_id or TENANT_ID),
        "role": role,
        "email": "test@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _make_app(exposure_repo=None, profile_repo=None):
    """Create a minimal FastAPI app with dependency overrides."""
    from fastapi import FastAPI
    from src.api.v1.scoring.geo_modifier import (
        router,
        get_exposure_repo,
        get_profile_repo,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/scoring")

    if exposure_repo is not None:
        async def _override_exposure():
            return exposure_repo
        app.dependency_overrides[get_exposure_repo] = _override_exposure

    if profile_repo is not None:
        async def _override_profile():
            return profile_repo
        app.dependency_overrides[get_profile_repo] = _override_profile

    return app


class TestReapplyGeoModifier:

    def test_valid_request_returns_202_and_queues_task(self):
        """Valid JWT + existing event_id → 202 Accepted, task enqueued."""
        from fastapi.testclient import TestClient

        event_id = uuid4()
        profile_id = uuid4()

        exposure_repo = AsyncMock()
        exposure_repo.get_by_event = AsyncMock(return_value=[MagicMock()])
        profile_repo = AsyncMock()
        profile_repo.get_by_id = AsyncMock(return_value=MagicMock())

        app = _make_app(exposure_repo=exposure_repo, profile_repo=profile_repo)

        with (
            patch(_SETTINGS_PATCH) as mock_settings,
            patch(_ENQUEUE_PATCH) as mock_enqueue,
        ):
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"

            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.post(
                    "/api/v1/scoring/geo-modifier/reapply",
                    json={"event_id": str(event_id), "profile_id": str(profile_id)},
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 202
        body = response.json()
        assert body["data"]["task_queued"] is True
        assert body["data"]["event_id"] == str(event_id)
        mock_enqueue.assert_called_once_with(
            event_id=str(event_id),
            tenant_id=str(TENANT_ID),
        )

    def test_missing_exposures_returns_404(self):
        """Event with no event_exposure rows → 404 with error envelope."""
        from fastapi.testclient import TestClient

        event_id = uuid4()
        profile_id = uuid4()

        exposure_repo = AsyncMock()
        exposure_repo.get_by_event = AsyncMock(return_value=[])  # empty
        profile_repo = AsyncMock()

        app = _make_app(exposure_repo=exposure_repo, profile_repo=profile_repo)

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"

            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.post(
                    "/api/v1/scoring/geo-modifier/reapply",
                    json={"event_id": str(event_id), "profile_id": str(profile_id)},
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["code"] == "EVENT_NOT_FOUND"

    def test_profile_wrong_tenant_returns_403(self):
        """profile_id belonging to a different tenant → 403."""
        from fastapi.testclient import TestClient

        event_id = uuid4()
        profile_id = uuid4()

        exposure_repo = AsyncMock()
        exposure_repo.get_by_event = AsyncMock(return_value=[MagicMock()])
        # Profile not found for this tenant → returns None → 403
        profile_repo = AsyncMock()
        profile_repo.get_by_id = AsyncMock(return_value=None)

        app = _make_app(exposure_repo=exposure_repo, profile_repo=profile_repo)

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"

            with TestClient(app) as client:
                token = _make_jwt_token(tenant_id=TENANT_ID)
                response = client.post(
                    "/api/v1/scoring/geo-modifier/reapply",
                    json={"event_id": str(event_id), "profile_id": str(profile_id)},
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 403

    def test_no_jwt_returns_401_or_403(self):
        """Request without JWT → 401 or 403."""
        from fastapi.testclient import TestClient

        event_id = uuid4()
        profile_id = uuid4()
        app = _make_app()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/scoring/geo-modifier/reapply",
                json={"event_id": str(event_id), "profile_id": str(profile_id)},
            )

        assert response.status_code in (401, 403)

    def test_non_uuid_event_id_returns_422(self):
        """Non-UUID event_id → 422 validation error."""
        from fastapi.testclient import TestClient

        # Provide dependency overrides so only body validation is tested
        exposure_repo = AsyncMock()
        profile_repo = AsyncMock()
        app = _make_app(exposure_repo=exposure_repo, profile_repo=profile_repo)

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value.JWT_SECRET_KEY = "test-secret"
            with TestClient(app) as client:
                token = _make_jwt_token()
                response = client.post(
                    "/api/v1/scoring/geo-modifier/reapply",
                    json={"event_id": "not-a-uuid", "profile_id": str(uuid4())},
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 422
