"""
Unit tests for TASK-009: evaluation router endpoints.

Tests auth (401/403), and basic routing/response structure.
Uses TestClient with dependency overrides; no real DB.

TDD: written before the implementation exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)
from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationSummary,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_eval_result() -> EvaluationResult:
    return EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={"factual_grounding": 0.9},
        overall_quality=0.85,
        prompt_version="v1",
        evaluated_at=datetime.now(tz=timezone.utc),
    )


def _make_golden_item() -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=uuid.uuid4(),
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY"},
        quality_metrics={"factual_grounding": 0.9},
        source="hand_authored",
        active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


def _make_calibration_result() -> CalibrationResult:
    from datetime import date
    return CalibrationResult(
        result_id=uuid.uuid4(),
        date=date(2026, 6, 1),
        action_signal="BUY",
        total_recommendations=25,
        direction_correct_pct=0.72,
        mean_confidence=0.78,
        computed_at=datetime.now(tz=timezone.utc),
    )


def _build_app(admin: bool = True) -> tuple[FastAPI, TestClient]:
    """Build a FastAPI test app with the evaluation router and mocked auth."""
    from src.api.evaluation.evaluation_router import evaluation_router
    from src.api.auth_deps import require_admin, get_current_user
    from src.api.auth_deps import CurrentUser

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/v1")

    if admin:
        admin_user = CurrentUser(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            role="admin",
            email="admin@test.com",
        )
        app.dependency_overrides[require_admin] = lambda: admin_user
        app.dependency_overrides[get_current_user] = lambda: admin_user
    else:
        non_admin = CurrentUser(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            role="operator",
            email="user@test.com",
        )
        from fastapi import HTTPException
        def _raise_forbidden():
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
        app.dependency_overrides[require_admin] = _raise_forbidden
        app.dependency_overrides[get_current_user] = lambda: non_admin

    return app, TestClient(app, raise_server_exceptions=False)


# ── GET /evaluation/results ──────────────────────────────────────────────────


def test_list_evaluation_results_returns_200():
    """GET /api/v1/evaluation/results should return 200 with list of results."""
    from src.api.evaluation import evaluation_router as router_module

    app, client = _build_app(admin=True)

    # Mock the service dependency
    eval_result = _make_eval_result()
    mock_service = AsyncMock()
    mock_service.list_recent = AsyncMock(return_value=[eval_result])

    with patch.object(
        router_module, "_get_evaluation_service", return_value=mock_service
    ):
        # Patch at the router function level
        pass

    # Use direct dependency override
    from src.api.evaluation.evaluation_router import get_evaluation_repo
    mock_repo = AsyncMock()
    mock_repo.list_recent = AsyncMock(return_value=[eval_result])
    app.dependency_overrides[get_evaluation_repo] = lambda: mock_repo

    response = client.get("/api/v1/evaluation/results")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_evaluation_results_forbidden_for_non_admin():
    """GET /api/v1/evaluation/results should return 403 for non-admin."""
    app, client = _build_app(admin=False)
    response = client.get("/api/v1/evaluation/results")
    assert response.status_code == 403


# ── GET /evaluation/golden-dataset ──────────────────────────────────────────


def test_list_golden_dataset_active_returns_200():
    """GET /api/v1/evaluation/golden-dataset should return 200."""
    from src.api.evaluation.evaluation_router import get_golden_dataset_repo

    app, client = _build_app(admin=True)
    item = _make_golden_item()
    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(return_value=[item])
    app.dependency_overrides[get_golden_dataset_repo] = lambda: mock_repo

    response = client.get("/api/v1/evaluation/golden-dataset")
    assert response.status_code == 200


# ── POST /evaluation/golden-dataset ─────────────────────────────────────────


def test_create_golden_dataset_item_returns_201():
    """POST /api/v1/evaluation/golden-dataset should return 201."""
    from src.api.evaluation.evaluation_router import get_golden_dataset_repo

    app, client = _build_app(admin=True)
    item = _make_golden_item()
    mock_repo = AsyncMock()
    mock_repo.create_item = AsyncMock(return_value=item)
    app.dependency_overrides[get_golden_dataset_repo] = lambda: mock_repo

    payload = {
        "input": {"query": "Analyse AAPL"},
        "expected_output": {"signal": "BUY"},
        "quality_metrics": {"factual_grounding": 0.9},
        "source": "hand_authored",
    }
    response = client.post("/api/v1/evaluation/golden-dataset", json=payload)
    assert response.status_code == 201


# ── GET /evaluation/calibration ──────────────────────────────────────────────


def test_list_calibration_returns_200():
    """GET /api/v1/evaluation/calibration should return 200."""
    from src.api.evaluation.evaluation_router import get_calibration_repo

    app, client = _build_app(admin=True)
    result = _make_calibration_result()
    mock_repo = AsyncMock()
    mock_repo.list_last_n_days = AsyncMock(return_value=[result])
    app.dependency_overrides[get_calibration_repo] = lambda: mock_repo

    response = client.get("/api/v1/evaluation/calibration")
    assert response.status_code == 200


# ── GET /evaluation/calibration/summary ──────────────────────────────────────


def test_calibration_summary_returns_200():
    """GET /api/v1/evaluation/calibration/summary should return 200."""
    from src.api.evaluation.evaluation_router import get_calibration_repo

    from datetime import date

    app, client = _build_app(admin=True)
    result = _make_calibration_result()
    mock_repo = AsyncMock()
    mock_repo.list_last_n_days = AsyncMock(return_value=[result])
    mock_repo.get_rolling_corr = AsyncMock(return_value=0.45)
    app.dependency_overrides[get_calibration_repo] = lambda: mock_repo

    response = client.get("/api/v1/evaluation/calibration/summary")
    assert response.status_code == 200
    data = response.json()
    assert "assessment" in data


# ── DELETE /evaluation/golden-dataset/{item_id} ──────────────────────────────


def test_delete_golden_dataset_item_returns_204():
    """DELETE /api/v1/evaluation/golden-dataset/{item_id} should return 204."""
    from src.api.evaluation.evaluation_router import get_golden_dataset_repo

    app, client = _build_app(admin=True)
    item_id = uuid.uuid4()
    mock_repo = AsyncMock()
    mock_repo.deactivate_item = AsyncMock(return_value=None)
    app.dependency_overrides[get_golden_dataset_repo] = lambda: mock_repo

    response = client.delete(f"/api/v1/evaluation/golden-dataset/{item_id}")
    assert response.status_code == 204
