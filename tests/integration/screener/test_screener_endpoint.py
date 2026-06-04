"""Integration tests for POST /api/v1/screener endpoint.

Uses FastAPI TestClient with dependency overrides for auth and ScreenerService.
No real DB connection is required — ScreenerService.run is patched with a stub
that returns controlled fixture data, and get_db is overridden with a no-op mock.

Covers:
- POST /api/v1/screener no filters → 200 paginated ScreenerResponse
- sort by custom_score desc places highest-scored company first
- cursor from first page → continuation without overlap
- unknown filter column → 422
- missing auth → 401
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import get_current_user, AuthenticatedUser
from src.api.v1.screener.router import router as screener_router
from src.api.v1.screener.schemas import ScreenerRow
from src.api.v1.screener.screener_service import encode_cursor


TENANT_ID = uuid4()
USER_ID = uuid4()

# ---------------------------------------------------------------------------
# Fixture data — three companies ordered by score descending
# ---------------------------------------------------------------------------

COMPANY_A_ID = uuid4()
COMPANY_B_ID = uuid4()
COMPANY_C_ID = uuid4()

_ALL_ROWS = [
    ScreenerRow(
        company_id=COMPANY_A_ID,
        ticker="AAPL",
        name="Apple Corp",
        sector="Technology",
        market_cap=3_000_000_000.0,
        custom_score=95.0,
        score_delta=5.0,
        current_price=180.0,
        active_events_count=2,
        active_event_categories=["geopolitical", "financial"],
    ),
    ScreenerRow(
        company_id=COMPANY_B_ID,
        ticker="MSFT",
        name="Microsoft Corp",
        sector="Technology",
        market_cap=2_500_000_000.0,
        custom_score=88.0,
        score_delta=3.0,
        current_price=320.0,
        active_events_count=1,
        active_event_categories=["financial"],
    ),
    ScreenerRow(
        company_id=COMPANY_C_ID,
        ticker="GOOG",
        name="Google Corp",
        sector="Technology",
        market_cap=1_800_000_000.0,
        custom_score=72.0,
        score_delta=-2.0,
        current_price=140.0,
        active_events_count=0,
        active_event_categories=[],
    ),
]


def _make_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id=USER_ID, tenant_id=TENANT_ID, role="end_user")


async def _mock_db():
    """No-op async DB session — service is patched so DB is never queried."""
    yield MagicMock()


def _make_test_app() -> FastAPI:
    """Create a minimal FastAPI app with only the screener router.

    Overrides get_db with a no-op mock so no real DB connection is required.
    """
    from src.api.dependencies import get_db

    test_app = FastAPI()
    test_app.include_router(screener_router, prefix="/api/v1")
    test_app.dependency_overrides[get_db] = _mock_db
    return test_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_service(monkeypatch):
    """Patch ScreenerService.run to avoid a real DB call."""
    import src.api.v1.screener.screener_service as svc_module

    async def _fake_run(self, request, tenant_id):
        if request.cursor:
            # Return the third row as the continuation page
            return [_ALL_ROWS[2]], None, len(_ALL_ROWS)
        # Return first two rows; third page token points to second row
        next_c = encode_cursor(_ALL_ROWS[1].custom_score, _ALL_ROWS[1].company_id)
        return list(_ALL_ROWS[:2]), next_c, len(_ALL_ROWS)

    monkeypatch.setattr(svc_module.ScreenerService, "run", _fake_run)


@pytest.fixture()
def client(patched_service):
    """TestClient with auth overridden."""
    app = _make_test_app()
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScreenerEndpointNoFilters:
    @pytest.mark.integration
    def test_post_no_filters_returns_200(self, client):
        """POST with no filters returns 200 and a ScreenerResponse envelope."""
        resp = client.post(
            "/api/v1/screener",
            json={"filters": [], "sort_column": "custom_score", "sort_dir": "desc", "page_size": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is None
        data = body["data"]
        assert "data" in data
        assert "next_cursor" in data
        assert "total_count" in data
        assert "applied_filters" in data

    @pytest.mark.integration
    def test_highest_score_first(self, client):
        """With sort_dir=desc the first row has the highest custom_score."""
        resp = client.post(
            "/api/v1/screener",
            json={"filters": [], "sort_column": "custom_score", "sort_dir": "desc", "page_size": 50},
        )
        assert resp.status_code == 200
        rows = resp.json()["data"]["data"]
        assert len(rows) >= 2
        # First row should have higher score than second
        assert rows[0]["custom_score"] >= rows[1]["custom_score"]

    @pytest.mark.integration
    def test_cursor_pagination_no_overlap(self, client):
        """Cursor from page 1 fetches page 2 without duplicate company IDs."""
        resp1 = client.post(
            "/api/v1/screener",
            json={"filters": [], "sort_column": "custom_score", "sort_dir": "desc", "page_size": 2},
        )
        assert resp1.status_code == 200
        body1 = resp1.json()["data"]
        next_cursor = body1["next_cursor"]
        assert next_cursor is not None

        page1_ids = {r["company_id"] for r in body1["data"]}

        resp2 = client.post(
            "/api/v1/screener",
            json={
                "filters": [],
                "sort_column": "custom_score",
                "sort_dir": "desc",
                "page_size": 2,
                "cursor": next_cursor,
            },
        )
        assert resp2.status_code == 200
        body2 = resp2.json()["data"]
        page2_ids = {r["company_id"] for r in body2["data"]}

        # No overlap between pages
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.integration
    def test_unknown_filter_column_returns_422(self, patched_service):
        """Filter on unknown column → 422 Unprocessable Entity."""
        app = _make_test_app()
        app.dependency_overrides[get_current_user] = lambda: _make_user()
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post(
                "/api/v1/screener",
                json={
                    "filters": [
                        {
                            "column": "DROP_TABLE",
                            "operator": "eq",
                            "value": "x",
                            "logical_op": "AND",
                        }
                    ],
                    "sort_column": "custom_score",
                    "sort_dir": "desc",
                    "page_size": 50,
                },
            )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_requires_auth(self):
        """Without auth override → 401 or 403 (bearer scheme requires token)."""
        app = _make_test_app()
        # No dependency override — real auth dependency will fire
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/screener",
                json={"filters": [], "sort_column": "custom_score", "sort_dir": "desc", "page_size": 50},
            )
        assert resp.status_code in (401, 403)
