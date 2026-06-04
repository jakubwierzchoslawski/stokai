"""
Integration tests for TASK-003: calibration review API endpoints.

Uses FastAPI TestClient with mocked repositories to avoid real DB operations.
Tests verify HTTP status codes, auth enforcement, and response shapes.

pytest.mark.integration — these tests require the application to be importable
but do not require a real DB.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.evaluation.schemas.calibration_review_schemas import CalibrationReview
from src.api.evaluation.evaluation_router import (
    evaluation_router,
    get_calibration_repo,
    get_calibration_review_repo,
)

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────

ADMIN_USER_ID = uuid.uuid4()
JWT_SECRET = "test-secret-key-minimum-32-characters-long!"


def _make_jwt(role: str = "admin", user_id: uuid.UUID | None = None) -> str:
    """Generate a minimal JWT for testing."""
    from datetime import timedelta

    from jose import jwt

    payload = {
        "sub": str(user_id or ADMIN_USER_ID),
        "tenant_id": str(uuid.uuid4()),
        "role": role,
        "email": f"{role}@example.com",
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _make_review(
    action_taken: str = "no_action",
    corr_at_review: float | None = 0.22,
    below_threshold: bool = False,
) -> CalibrationReview:
    return CalibrationReview(
        review_id=uuid.uuid4(),
        reviewed_by=ADMIN_USER_ID,
        reviewed_at=datetime.now(tz=timezone.utc),
        corr_at_review=corr_at_review,
        below_threshold=below_threshold,
        action_taken=action_taken,
        notes=None,
    )


def _build_app(
    mock_cal_repo: AsyncMock | None = None,
    mock_review_repo: AsyncMock | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app with the evaluation router and mocked deps."""
    import os

    os.environ.setdefault("JWT_SECRET_KEY", JWT_SECRET)

    app = FastAPI()
    # The router already carries prefix="/evaluation"; mounting at "/api/v1" produces
    # the correct "/api/v1/evaluation/..." paths that the tests assert against.
    app.include_router(evaluation_router, prefix="/api/v1")

    if mock_cal_repo is not None:
        app.dependency_overrides[get_calibration_repo] = lambda: mock_cal_repo
    if mock_review_repo is not None:
        app.dependency_overrides[get_calibration_review_repo] = lambda: mock_review_repo

    return app


# ── POST /calibration/reviews ─────────────────────────────────────────────────


def test_post_review_unauthenticated_returns_401():
    """POST without Authorization header must return 401."""
    app = _build_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/evaluation/calibration/reviews",
            json={"action_taken": "no_action"},
        )
    assert response.status_code == 401


def test_post_review_non_admin_returns_403():
    """POST with operator role must return 403."""
    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=_make_review())

    app = _build_app(mock_cal_repo, mock_review_repo)
    token = _make_jwt(role="operator")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/evaluation/calibration/reviews",
            json={"action_taken": "no_action"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


def test_post_review_admin_improvement_loop_returns_201_with_review_id():
    """POST by admin with 'improvement_loop_triggered' returns 201 with review_id."""
    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    expected_review = _make_review(
        action_taken="improvement_loop_triggered",
        corr_at_review=0.22,
        below_threshold=True,
    )
    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=expected_review)

    app = _build_app(mock_cal_repo, mock_review_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/api/v1/evaluation/calibration/reviews",
            json={"action_taken": "improvement_loop_triggered"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    data = response.json()
    assert "review_id" in data
    assert data["action_taken"] == "improvement_loop_triggered"


def test_post_review_reads_corr_at_review_from_calibration_repo():
    """Endpoint must pass corr_at_review read from CalibrationRepository.get_rolling_corr."""
    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    expected_review = _make_review(corr_at_review=0.22)
    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=expected_review)

    app = _build_app(mock_cal_repo, mock_review_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/api/v1/evaluation/calibration/reviews",
            json={"action_taken": "no_action"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["corr_at_review"] == pytest.approx(0.22)
    mock_cal_repo.get_rolling_corr.assert_called_once()


# ── GET /calibration/reviews ──────────────────────────────────────────────────


def test_get_reviews_admin_returns_list_in_desc_order():
    """GET by admin returns list of reviews in descending reviewed_at order."""
    t1 = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)

    reviews = []
    for ts in [t3, t2, t1]:
        r = _make_review()
        # Override reviewed_at via dict reconstruction
        reviews.append(
            CalibrationReview(
                review_id=uuid.uuid4(),
                reviewed_by=ADMIN_USER_ID,
                reviewed_at=ts,
                corr_at_review=0.3,
                below_threshold=False,
                action_taken="no_action",
                notes=None,
            )
        )

    mock_cal_repo = AsyncMock()
    mock_review_repo = AsyncMock()
    mock_review_repo.list_recent = AsyncMock(return_value=reviews)

    app = _build_app(mock_cal_repo, mock_review_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/reviews",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    # Verify descending order by reviewed_at
    dates = [d["reviewed_at"] for d in data]
    assert dates == sorted(dates, reverse=True)


def test_get_reviews_non_admin_returns_403():
    """GET with operator role must return 403."""
    mock_cal_repo = AsyncMock()
    mock_review_repo = AsyncMock()

    app = _build_app(mock_cal_repo, mock_review_repo)
    token = _make_jwt(role="operator")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/reviews",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
