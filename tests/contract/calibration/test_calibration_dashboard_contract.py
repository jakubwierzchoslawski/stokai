"""
Contract tests for TASK-006: calibration dashboard HTTP API.

HTTP-level TestClient tests verifying:
1. GET /api/v1/evaluation/calibration?days=30 returns list with required fields
2. GET /api/v1/evaluation/calibration/summary returns required fields with correct types
3. assessment is exactly one of the three allowed values
4. Non-admin → 403 on both endpoints

No real DB required — repositories are mocked.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationSummary,
)
from src.api.evaluation.evaluation_router import (
    evaluation_router,
    get_calibration_repo,
    get_calibration_review_repo,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

JWT_SECRET = "test-secret-key-minimum-32-characters-long!"
ADMIN_USER_ID = uuid.uuid4()

ALLOWED_ASSESSMENTS = frozenset(
    {
        "Healthy",
        "Warning: CORR below threshold — improvement loop recommended",
        "Insufficient data",
    }
)


def _make_jwt(role: str = "admin") -> str:
    from datetime import timedelta

    from jose import jwt

    payload = {
        "sub": str(ADMIN_USER_ID),
        "tenant_id": str(uuid.uuid4()),
        "role": role,
        "email": f"{role}@example.com",
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _make_calibration_result() -> CalibrationResult:
    return CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal="BUY_OPP",
        total_recommendations=10,
        direction_correct_pct=0.7,
        corr_confidence_actual=0.45,
        mean_confidence=0.75,
        computed_at=datetime.now(tz=timezone.utc),
    )


def _build_app(
    mock_cal_repo: AsyncMock,
    mock_review_repo: AsyncMock | None = None,
) -> FastAPI:
    import os

    os.environ.setdefault("JWT_SECRET_KEY", JWT_SECRET)

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/v1/evaluation")
    app.dependency_overrides[get_calibration_repo] = lambda: mock_cal_repo
    if mock_review_repo is not None:
        app.dependency_overrides[get_calibration_review_repo] = lambda: mock_review_repo
    else:
        stub = AsyncMock()
        app.dependency_overrides[get_calibration_review_repo] = lambda: stub
    return app


# ── Contract test 1: GET /calibration returns required fields ─────────────────


def test_calibration_list_returns_required_fields():
    """
    GET /api/v1/evaluation/calibration?days=30 returns list with:
    date, action_signal, corr_confidence_actual, direction_correct_pct, mean_confidence.
    """
    mock_cal_repo = AsyncMock()
    mock_cal_repo.list_last_n_days = AsyncMock(
        return_value=[_make_calibration_result()]
    )

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/evaluation/calibration",
            params={"days": 30},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    row = data[0]
    assert "date" in row
    assert "action_signal" in row
    assert "corr_confidence_actual" in row
    assert "direction_correct_pct" in row
    assert "mean_confidence" in row


# ── Contract test 2: GET /calibration/summary returns required fields ─────────


def test_calibration_summary_returns_required_fields():
    """
    GET /api/v1/evaluation/calibration/summary returns:
    rolling_corr, below_threshold, per_signal_accuracy, total_recommendations, assessment.
    """
    mock_cal_repo = AsyncMock()
    results = [_make_calibration_result() for _ in range(3)]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.45)

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()

    assert "rolling_corr" in data
    assert "below_threshold" in data
    assert "per_signal_accuracy" in data
    assert "total_recommendations" in data
    assert "assessment" in data

    # Type checks
    assert isinstance(data["below_threshold"], bool)
    assert isinstance(data["per_signal_accuracy"], dict)
    assert isinstance(data["total_recommendations"], int)


# ── Contract test 3: assessment is one of the three allowed values ────────────


@pytest.mark.parametrize(
    "rolling_corr, total_recs, expected_assessment",
    [
        (0.45, 30, "Healthy"),
        (0.15, 30, "Warning: CORR below threshold — improvement loop recommended"),
        (0.1, 5, "Insufficient data"),
    ],
)
def test_assessment_is_valid_enum_value(rolling_corr, total_recs, expected_assessment):
    """assessment must be exactly one of the three allowed strings."""
    from math import ceil

    mock_cal_repo = AsyncMock()
    n_results = max(1, ceil(total_recs / 10))
    recs_per = total_recs // n_results

    results = [
        CalibrationResult(
            result_id=uuid.uuid4(),
            date=date(2026, 6, 1),
            action_signal="BUY",
            total_recommendations=recs_per,
            direction_correct_pct=0.7,
            corr_confidence_actual=rolling_corr,
            mean_confidence=0.75,
            computed_at=datetime.now(tz=timezone.utc),
        )
        for _ in range(n_results)
    ]
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=results)
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=rolling_corr)

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="admin")

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assessment = data["assessment"]

    assert assessment in ALLOWED_ASSESSMENTS, (
        f"assessment={assessment!r} is not in {ALLOWED_ASSESSMENTS}"
    )
    assert assessment == expected_assessment


# ── Contract test 4: Non-admin gets 403 on both endpoints ────────────────────


def test_calibration_list_non_admin_returns_403():
    """GET /calibration with operator role → 403."""
    mock_cal_repo = AsyncMock()
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=[])

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="operator")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/evaluation/calibration",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


def test_calibration_summary_non_admin_returns_403():
    """GET /calibration/summary with operator role → 403."""
    mock_cal_repo = AsyncMock()
    mock_cal_repo.list_last_n_days = AsyncMock(return_value=[])
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=None)

    app = _build_app(mock_cal_repo)
    token = _make_jwt(role="operator")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/evaluation/calibration/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
