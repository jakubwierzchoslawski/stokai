"""
Unit + integration tests for DisclaimerMiddleware — TDD for TASK-002.

Unit tests: _inject_disclaimer logic only (no ASGI).
Integration tests: via ASGI test client with a minimal FastAPI test app.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from httpx import ASGITransport, AsyncClient

from src.api.middleware.disclaimer_middleware import (
    DISCLAIMER_FIELD,
    DisclaimerMiddleware,
)

THRESHOLD = 5
TEXT = "Based on fewer than 5 historical cases — treat with caution"


# ── Unit tests: _inject_disclaimer ────────────────────────────────────────────


def _mw() -> DisclaimerMiddleware:
    """Create a bare middleware instance for unit testing _inject_disclaimer."""
    # Use a dummy ASGI app; we only need the middleware object, not its dispatch.
    dummy_app = FastAPI()
    return DisclaimerMiddleware(
        app=dummy_app,
        threshold=THRESHOLD,
        disclaimer_text=TEXT,
        path_prefixes=[],  # unrestricted for unit tests
    )


def test_inject_disclaimer_flat_dict_below_threshold() -> None:
    """A flat dict with sample_size < threshold gains a disclaimer key."""
    mw = _mw()
    data = {"sample_size": 3, "action": "HOLD"}
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert result[DISCLAIMER_FIELD] == TEXT


def test_inject_disclaimer_sample_size_equal_threshold_no_injection() -> None:
    """sample_size == threshold (not strictly less-than) → no disclaimer."""
    mw = _mw()
    data = {"sample_size": 5, "action": "HOLD"}
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert DISCLAIMER_FIELD not in result


def test_inject_disclaimer_sample_size_above_threshold_no_injection() -> None:
    """sample_size > threshold → no disclaimer."""
    mw = _mw()
    data = {"sample_size": 6, "action": "HOLD"}
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert DISCLAIMER_FIELD not in result


def test_inject_disclaimer_dict_without_sample_size_unchanged() -> None:
    """Dict without sample_size key is returned structurally unchanged."""
    mw = _mw()
    data = {"action": "HOLD", "confidence": 0.8}
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert DISCLAIMER_FIELD not in result
    assert result == data


def test_inject_disclaimer_nested_structure() -> None:
    """Disclaimer injected only into the nested dict with sample_size < threshold."""
    mw = _mw()
    data = {
        "recommendation": {"sample_size": 2, "action": "HOLD"},
        "meta": {},
    }
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert result["recommendation"][DISCLAIMER_FIELD] == TEXT
    assert DISCLAIMER_FIELD not in result["meta"]
    assert DISCLAIMER_FIELD not in result  # top-level has no sample_size


def test_inject_disclaimer_list_partial_injection() -> None:
    """In a list of recs, only those with sample_size < threshold get the disclaimer."""
    mw = _mw()
    data = [
        {"sample_size": 1, "action": "BUY_OPP"},
        {"sample_size": 1, "action": "HOLD"},
        {"sample_size": 10, "action": "WATCH"},
    ]
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    assert result[0][DISCLAIMER_FIELD] == TEXT
    assert result[1][DISCLAIMER_FIELD] == TEXT
    assert DISCLAIMER_FIELD not in result[2]


def test_inject_disclaimer_idempotent_already_present() -> None:
    """Disclaimer key that already exists is not duplicated / overwritten."""
    mw = _mw()
    existing_disclaimer = "custom disclaimer"
    data = {
        "sample_size": 2,
        "action": "HOLD",
        DISCLAIMER_FIELD: existing_disclaimer,
    }
    result = mw._inject_disclaimer(data, THRESHOLD, TEXT)
    # Existing disclaimer must not be replaced
    assert result[DISCLAIMER_FIELD] == existing_disclaimer


# ── Integration tests: ASGI test client ───────────────────────────────────────


def _make_test_app(path_prefixes: list[str] | None = None) -> FastAPI:
    """Build a minimal FastAPI app with DisclaimerMiddleware wired in."""
    test_app = FastAPI()
    test_app.add_middleware(
        DisclaimerMiddleware,
        threshold=THRESHOLD,
        disclaimer_text=TEXT,
        path_prefixes=path_prefixes if path_prefixes is not None else [],
    )

    @test_app.get("/recommendation/low-sample")
    async def low_sample() -> dict:
        return {"sample_size": 2, "action_signal": "HOLD"}

    @test_app.get("/recommendation/high-sample")
    async def high_sample() -> dict:
        return {"sample_size": 10, "action_signal": "HOLD"}

    @test_app.get("/html-endpoint")
    async def html_endpoint() -> HTMLResponse:
        return HTMLResponse(content="<html><body>Hello</body></html>")

    @test_app.get("/recommendation/no-sample-size")
    async def no_sample_size() -> dict:
        return {"action_signal": "HOLD", "confidence": 0.8}

    return test_app


@pytest.mark.asyncio
async def test_middleware_injects_disclaimer_on_low_sample_response() -> None:
    """Endpoint returning sample_size=2 should have 'disclaimer' in response."""
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendation/low-sample")
    body = resp.json()
    assert DISCLAIMER_FIELD in body
    assert body[DISCLAIMER_FIELD] == TEXT


@pytest.mark.asyncio
async def test_middleware_does_not_inject_on_html_response() -> None:
    """Non-JSON (text/html) responses pass through unchanged."""
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/html-endpoint")
    assert resp.status_code == 200
    assert DISCLAIMER_FIELD.encode() not in resp.content


@pytest.mark.asyncio
async def test_middleware_does_not_inject_when_no_sample_size() -> None:
    """JSON response without sample_size passes through unchanged."""
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendation/no-sample-size")
    body = resp.json()
    assert DISCLAIMER_FIELD not in body


@pytest.mark.asyncio
async def test_middleware_does_not_inject_on_high_sample_response() -> None:
    """Endpoint returning sample_size=10 should NOT have 'disclaimer'."""
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/recommendation/high-sample")
    body = resp.json()
    assert DISCLAIMER_FIELD not in body
