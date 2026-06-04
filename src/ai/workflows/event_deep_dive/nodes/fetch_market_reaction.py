"""
ai.workflows.event_deep_dive.nodes.fetch_market_reaction — DeterministicNode.

Calls the get_price_reaction_to_event tool per exposed company and writes
state.market_reaction as dict[str, PriceReaction].

If the market is closed (no data available / tool returns None), the reaction
for that company is omitted — this is NOT an error.

PLAN-F-010 TASK-005.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Any
from uuid import UUID

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, PriceReaction

logger = logging.getLogger(__name__)

# NYSE trading hours (UTC): 14:30 – 21:00
_MARKET_OPEN_UTC = time(14, 30)
_MARKET_CLOSE_UTC = time(21, 0)


def _is_market_open() -> bool:
    """Return True if NYSE is currently open (simplified weekday check)."""
    now = datetime.now(tz=timezone.utc)
    if now.weekday() >= 5:  # Saturday / Sunday
        return False
    return _MARKET_OPEN_UTC <= now.time() <= _MARKET_CLOSE_UTC


async def fetch_market_reaction_so_far(
    state: DeepDiveWorkflowState,
    *,
    price_tool: Any,
) -> DeepDiveWorkflowState:
    """Fetch current price reactions for all exposed companies.

    Iterates over state.event_full.exposures, calls price_tool per company,
    and writes state.market_reaction.

    Args:
        state: Current DeepDiveWorkflowState (event_full must be set).
        price_tool: Callable with signature
            async get_price_reaction(event_id, company_id) -> dict | None.
            Returns None when no data is available (market closed, etc.).

    Returns:
        Updated state with market_reaction populated.
    """
    if state.event_full is None:
        logger.warning("fetch_market_reaction_so_far: event_full is None — skipping")
        return state

    reactions: dict[str, PriceReaction] = {}

    if not _is_market_open():
        logger.info(
            "fetch_market_reaction_so_far: market is closed — "
            "storing empty reactions for event_id=%s",
            state.event_full.event_id,
        )
        return state.model_copy(update={"market_reaction": reactions})

    event_id = state.event_full.event_id

    for exposure in state.event_full.exposures:
        company_id_raw = (
            exposure.get("company_id") if isinstance(exposure, dict)
            else getattr(exposure, "company_id", None)
        )
        if company_id_raw is None:
            continue

        company_id = UUID(str(company_id_raw))

        try:
            raw = await price_tool.get_price_reaction(
                event_id=event_id, company_id=company_id
            )
            if raw is None:
                continue

            ticker = (
                raw.get("ticker", "") if isinstance(raw, dict)
                else getattr(raw, "ticker", "")
            )

            reaction = PriceReaction(
                company_id=company_id,
                ticker=ticker,
                price_before=raw.get("price_before") if isinstance(raw, dict) else getattr(raw, "price_before", None),
                price_after=raw.get("price_after") if isinstance(raw, dict) else getattr(raw, "price_after", None),
                change_pct=raw.get("change_pct") if isinstance(raw, dict) else getattr(raw, "change_pct", None),
                volume_ratio=raw.get("volume_ratio") if isinstance(raw, dict) else getattr(raw, "volume_ratio", None),
                sampled_at=raw.get("sampled_at") if isinstance(raw, dict) else getattr(raw, "sampled_at", None),
            )
            reactions[str(company_id)] = reaction

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fetch_market_reaction_so_far: price_tool failed for company_id=%s: %s",
                company_id,
                exc,
            )

    logger.info(
        "fetch_market_reaction_so_far: collected %d reactions for event_id=%s",
        len(reactions),
        event_id,
    )
    return state.model_copy(update={"market_reaction": reactions})
