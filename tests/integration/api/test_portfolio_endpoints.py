"""
tests.integration.api.test_portfolio_endpoints

Integration tests for portfolio and watchlist API endpoints using FastAPI TestClient
with mocked services via dependency_overrides.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth_deps import get_current_user, CurrentUser
from src.api.routers.portfolio_router import (
    _get_portfolio_service,
    _get_csv_import_service,
)
from src.api.routers.watchlist_router import _get_watchlist_service
from src.portfolio.csv_import_service import CsvImportResult, CsvRowError
from src.portfolio.exceptions import NotFoundError
from src.storage.models.portfolio import Portfolio, Position, WatchlistItem


# ── Shared fixtures ────────────────────────────────────────────────────────────


TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PORTFOLIO_ID = uuid.uuid4()
POSITION_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role="end_user",
        email="test@test.com",
    )


def _make_portfolio(**kwargs) -> Portfolio:
    defaults = dict(
        portfolio_id=PORTFOLIO_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        name="Test Portfolio",
        created_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return Portfolio(**defaults)


def _make_position(**kwargs) -> Position:
    defaults = dict(
        position_id=POSITION_ID,
        portfolio_id=PORTFOLIO_ID,
        company_id=COMPANY_ID,
        ticker="AAPL",
        shares=10.0,
        cost_basis=150.0,
        added_at=datetime.utcnow(),
        source="manual",
    )
    defaults.update(kwargs)
    return Position(**defaults)


def _make_watchlist_item(**kwargs) -> WatchlistItem:
    defaults = dict(
        item_id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        company_id=COMPANY_ID,
        ticker="AAPL",
        added_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return WatchlistItem(**defaults)


# ── Portfolio tests ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_portfolio_returns_201():
    mock_svc = AsyncMock()
    mock_svc.create_portfolio.return_value = _make_portfolio()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_portfolio_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/portfolios",
                json={"name": "Test Portfolio"},
            )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Test Portfolio"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_list_portfolios_empty():
    mock_svc = AsyncMock()
    mock_svc.list_portfolios.return_value = []

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_portfolio_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/portfolios")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_add_position_returns_201():
    mock_svc = AsyncMock()
    mock_svc.add_position.return_value = _make_position()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_portfolio_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/portfolios/{PORTFOLIO_ID}/positions",
                json={"ticker": "AAPL", "shares": 10.0},
            )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["ticker"] == "AAPL"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_delete_position_removes_from_list():
    mock_svc = AsyncMock()
    mock_svc.delete_position.return_value = None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_portfolio_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.delete(
                f"/api/v1/portfolios/{PORTFOLIO_ID}/positions/{POSITION_ID}"
            )
        assert resp.status_code == 204
        mock_svc.delete_position.assert_awaited_once_with(TENANT_ID, POSITION_ID)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_csv_import_partial_errors_returns_200_with_error_report():
    mock_csv_svc = AsyncMock()
    mock_csv_svc.import_csv.return_value = CsvImportResult(
        positions_created=2,
        errors=[CsvRowError(row_number=2, ticker="BAD", error="invalid shares")],
    )

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_csv_import_service] = lambda: mock_csv_svc

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/portfolios/import",
                data={"portfolio_id": str(PORTFOLIO_ID)},
                files={"file": ("test.csv", b"ticker,shares\nAAPL,10\nBAD,abc", "text/csv")},
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["positions_created"] == 2
        assert len(data["errors"]) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_portfolio_router_requires_auth():
    """Unauthenticated request returns 403 (HTTPBearer auto_error=True)."""
    # Clear overrides to use real auth (which will reject missing token)
    app.dependency_overrides.clear()

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/portfolios")

    # HTTPBearer with auto_error=True returns 403 when no auth header
    assert resp.status_code in (401, 403)


# ── Watchlist tests ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_watchlist_add_returns_201():
    mock_svc = AsyncMock()
    mock_svc.add_to_watchlist.return_value = _make_watchlist_item()

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_watchlist_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/watchlist",
                json={"company_id": str(COMPANY_ID), "ticker": "AAPL"},
            )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["ticker"] == "AAPL"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_watchlist_get_empty_returns_empty_array():
    mock_svc = AsyncMock()
    mock_svc.list_watchlist.return_value = []

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_watchlist_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/watchlist")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_watchlist_delete_removes_item():
    mock_svc = AsyncMock()
    mock_svc.remove_from_watchlist.return_value = None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_watchlist_service] = lambda: mock_svc

    try:
        with TestClient(app) as client:
            resp = client.delete(f"/api/v1/watchlist/{COMPANY_ID}")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()
