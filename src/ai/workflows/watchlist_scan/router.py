"""
ai.workflows.watchlist_scan.router — Confidence router for the Watchlist Scan.

Pure routing function applying D9 confidence thresholds after evaluate_quality.
Used as the LangGraph conditional edge routing function.

  >= 0.70  → "dispatch"         (auto-send path, targets 18:00 delivery)
  >= 0.40  → "hil_enqueue"      (human-in-the-loop, deadline 17:45)
  < 0.40   → "block_and_notify" (blocked — confidence too low)

PLAN-F-008 TASK-012
"""
from __future__ import annotations

from typing import Literal

from src.ai.workflows.watchlist_scan.state import WatchlistScanState

# D9 confidence thresholds
_AUTO_DISPATCH_THRESHOLD = 0.70
_HIL_THRESHOLD = 0.40


def route_after_quality(
    state: WatchlistScanState,
) -> Literal["dispatch", "hil_enqueue", "block_and_notify"]:
    """LangGraph conditional edge router from evaluate_quality.

    Routes based on state.overall_confidence using D9 thresholds:
      >= 0.70  → "dispatch"         (auto-send path)
      >= 0.40  → "hil_enqueue"      (human-in-the-loop path)
      < 0.40   → "block_and_notify" (blocked — confidence too low)

    The 0.70 boundary is inclusive (dispatch), and the 0.40 boundary is
    inclusive (hil_enqueue).

    Args:
        state: Current WatchlistScanState after evaluate_quality_node runs.

    Returns:
        Node name string for LangGraph conditional edge routing.
    """
    confidence = state.overall_confidence

    if confidence >= _AUTO_DISPATCH_THRESHOLD:
        return "dispatch"
    elif confidence >= _HIL_THRESHOLD:
        return "hil_enqueue"
    else:
        return "block_and_notify"
