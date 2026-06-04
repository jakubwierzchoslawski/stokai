"""
ai.workflows — LangGraph-based workflow orchestration for StokAI.

Sub-packages:
  on_demand      — Workflow 2: On-Demand Company Analysis (Mode B)
  watchlist_scan — Workflow 3: Watchlist Scan (Mode B, PLAN-F-008)

Workflow registry:
  WORKFLOW_REGISTRY maps workflow_id → factory function.
  build_watchlist_scan_graph is registered so it is discovered at startup.

WorkflowStructureValidator is called inside each graph factory at startup.
Validation result is logged at INFO level (AC-005).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Workflow registry ─────────────────────────────────────────────────────────

WORKFLOW_REGISTRY: dict = {}


def _register_watchlist_scan() -> None:
    """Register the watchlist scan workflow in the registry."""
    try:
        from src.ai.workflows.watchlist_scan.graph import build_watchlist_scan_graph

        WORKFLOW_REGISTRY["watchlist_scan"] = build_watchlist_scan_graph
        logger.info(
            "ai.workflows: registered 'watchlist_scan' workflow "
            "(build_watchlist_scan_graph)"
        )
    except Exception as exc:
        logger.error(
            "ai.workflows: failed to register 'watchlist_scan' workflow: %s", exc
        )


# Register workflows at module import time
_register_watchlist_scan()
