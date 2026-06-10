def test_all_required_routers_mounted():
    """Verify that all Phase 2b routes are registered in the app."""
    from src.api.main import app

    paths = {route.path for route in app.routes}

    assert any("/events" in p for p in paths), "events v1 router not mounted"
    assert any("/events/{event_id}/popup" in p for p in paths), "disclosure router not mounted"
    assert any("/briefs" in p for p in paths), "briefs router not mounted"
    assert any("/companies/{company_id}/detail" in p for p in paths), "company-detail router not mounted"
    assert any("/admin/audit/decisions" in p for p in paths), "audit router not mounted"
