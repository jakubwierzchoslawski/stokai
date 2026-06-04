"""
tests.ai.workflows.morning_brief.test_morning_brief_renderer
— TDD tests for the responsive morning brief email renderer.

Tests written first (red phase) per PLAN-N-014 TASK-009.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Ensure src is on sys.path ─────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Minimal report data fixture ───────────────────────────────────────────────

MINIMAL_REPORT_DATA = {
    "brief_id": "brief-test-001",
    "workflow_id": "wf-test-001",
    "brief_date": "4 June 2026",
    "generated_at": "2026-06-04T06:00:00Z",
    "confidence": 0.82,
    "score_changes": [],
    "relevant_events": [],
    "narrative": "",
    "recommendations": [],
    "why_link": "https://stokai.example.com/why",
    "unsubscribe_link": "https://stokai.example.com/unsubscribe",
    "settings_link": "https://stokai.example.com/settings",
}

REPORT_WITH_RECOMMENDATIONS = {
    **MINIMAL_REPORT_DATA,
    "recommendations": [
        {
            "ticker": "AAPL",
            "company_id": "aapl",
            "action_signal": "BUY_OPP",
            "rationale": "Strong earnings beat with upward guidance revision.",
        },
        {
            "ticker": "TSLA",
            "company_id": "tsla",
            "action_signal": "REDUCE_RISK",
            "rationale": "Regulatory headwinds in EU market.",
        },
        {
            "ticker": "MSFT",
            "company_id": "msft",
            "action_signal": "HOLD",
            "rationale": "Stable cloud growth; no catalyst expected.",
        },
    ],
}


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestMorningBriefRenderer:
    """TDD tests for MorningBriefRenderer.render()."""

    @pytest.fixture(autouse=True)
    def renderer(self):
        """Instantiate renderer; skip if jinja2 not installed."""
        pytest.importorskip("jinja2")
        from src.alerts.services.morning_brief_renderer import MorningBriefRenderer

        self.renderer = MorningBriefRenderer()

    def test_rendered_html_contains_responsive_media_query(self):
        """AC-002: rendered HTML must contain the responsive @media query block."""
        html = self.renderer.render(MINIMAL_REPORT_DATA)
        assert "@media only screen and (max-width: 600px)" in html

    def test_rendered_html_has_no_external_stylesheet_link(self):
        """Email constraint: no <link rel='stylesheet'> — all CSS must be inline."""
        html = self.renderer.render(MINIMAL_REPORT_DATA)
        assert '<link rel="stylesheet"' not in html
        assert "<link rel='stylesheet'" not in html

    def test_rendered_html_contains_all_recommendations(self):
        """All recommendation blocks must appear in the rendered output."""
        html = self.renderer.render(REPORT_WITH_RECOMMENDATIONS)
        # All three tickers should appear
        assert "AAPL" in html
        assert "TSLA" in html
        assert "MSFT" in html

    def test_render_returns_valid_html_document(self):
        """render() must return a string starting with <!DOCTYPE html>."""
        html = self.renderer.render(MINIMAL_REPORT_DATA)
        assert isinstance(html, str)
        assert html.strip().lower().startswith("<!doctype html>")

    def test_rendered_html_contains_two_col_collapse_classes(self):
        """The two-col-left / two-col-right classes must appear for score card layout."""
        report = {
            **MINIMAL_REPORT_DATA,
            "score_changes": [
                {"ticker": "AAPL", "company_id": "aapl", "company_name": "Apple", "delta": 1.5},
                {"ticker": "TSLA", "company_id": "tsla", "company_name": "Tesla", "delta": -0.8},
            ],
        }
        html = self.renderer.render(report)
        assert "two-col-left" in html
        assert "two-col-right" in html

    def test_rendered_html_min_font_size_14px_in_body_copy(self):
        """Body copy font size must be at least 14px (AC-002: readability at 375px)."""
        html = self.renderer.render(MINIMAL_REPORT_DATA)
        # The .narrative and .event-summary classes have font-size: 14px in the template
        assert "font-size: 14px" in html

    def test_rendered_html_section_titles_18px(self):
        """Section titles must be at least 18px (AC-002: readability at 375px)."""
        html = self.renderer.render(MINIMAL_REPORT_DATA)
        assert "font-size: 18px" in html
