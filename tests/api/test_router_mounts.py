import pytest


def test_all_required_routers_mounted():
    """Verify that all Phase 2b routes are registered in the app."""
    from src.api.main import app

    paths = {route.path for route in app.routes}

    assert "/api/v1/events" in paths, "events v1 router not mounted at /api/v1/events"
    assert any("/api/v1/events/{event_id}/popup" in p for p in paths), "disclosure router not mounted"
    assert any("/api/v1/briefs" in p for p in paths), "briefs router not mounted"
    assert any("/api/v1/companies/{company_id}/detail" in p for p in paths), "company-detail router not mounted"
    assert any("/api/v1/admin/audit/decisions" in p for p in paths), "audit router not mounted"
