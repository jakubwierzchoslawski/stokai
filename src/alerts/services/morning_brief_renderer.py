"""
src.alerts.services.morning_brief_renderer — Responsive morning brief email renderer.

Loads the responsive HTML email template from
  src/email/templates/morning-brief-email.html
and renders it via Jinja2 with the provided report data dict.

The template uses inline CSS + a media query @media block to collapse to a
single-column layout at ≤600px, covering the 375px iPhone SE viewport (AC-002).

No external stylesheets are used — email client restriction per ARCHITECTURE.md §14.

Usage:
    from src.alerts.services.morning_brief_renderer import MorningBriefRenderer

    renderer = MorningBriefRenderer()
    html = renderer.render(report_data)

PLAN-N-014 TASK-009
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    _JINJA2_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JINJA2_AVAILABLE = False

# ── Template path ─────────────────────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "email" / "templates"
_TEMPLATE_NAME = "morning-brief-email.html"


class MorningBriefRenderer:
    """Renders the responsive Morning Brief HTML email template.

    The renderer is stateless — create one instance and call render() for each
    brief. Jinja2 auto-escaping is enabled for HTML output safety.

    Example report_data keys (all optional except those marked *required*):
        brief_id*      : str — unique brief identifier
        workflow_id*   : str — originating workflow run id
        brief_date*    : str — human-readable date, e.g. "4 June 2026"
        generated_at*  : str — ISO timestamp of generation
        confidence*    : float — [0, 1] confidence score
        score_changes  : list[dict] — portfolio score deltas
        relevant_events: list[dict] — overnight event summaries
        narrative      : str — HTML narrative body (safe=True in template)
        recommendations: list[dict] — action recommendations
        why_link*      : str — explain-my-brief URL
        unsubscribe_link*: str
        settings_link* : str
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or _TEMPLATE_DIR

        if not _JINJA2_AVAILABLE:
            raise ImportError(
                "jinja2 is required for MorningBriefRenderer. "
                "Install it via: pip install jinja2"
            )

        self._env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    def render(self, report_data: dict[str, Any]) -> str:
        """Render the responsive email template with report_data.

        Args:
            report_data: Dict of template variables. See class docstring for keys.

        Returns:
            Rendered HTML string starting with '<!DOCTYPE html>'.

        Raises:
            jinja2.TemplateNotFound: if the template file is missing.
        """
        template = self._env.get_template(_TEMPLATE_NAME)
        html = template.render(**report_data)
        return html
