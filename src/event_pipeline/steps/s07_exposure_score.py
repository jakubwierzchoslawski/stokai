"""Step 7: EXPOSURE SCORE — compute per-portfolio exposure scores with inputs_hash.

Architecture enforcement:
  P-03 Inputs-Hash Invalidation — recompute only when inputs_hash changes.
  P-08 Immutable — old score records are preserved (INSERT only, never UPDATE).
  AC-001 — fills exposure_map for each affected portfolio.
  AC-004 — geo_weight applied via ConcreteScoringPipeline (PLAN-F-003 TASK-014).

Single Responsibility: wires ScoringPipeline into Mode A pipeline at step 7.
Dependency Inversion: scoring_engine and repo are both injected.

TASK-014 extension:
  ExposureScoreStep now accepts an optional ``scoring_engine`` parameter.
  When provided (production mode), it delegates recomputation to
  ``ConcreteScoringPipeline.recompute_if_stale()`` for each portfolio holding
  affected by the incoming event, using an ``InputSnapshot`` derived from the
  event's company data.  If the engine returns ``None`` (hash unchanged), the
  pipeline continues without appending a new score — preserving AC-001.

  When ``scoring_engine`` is None (legacy / test mode), the step falls back
  to the original inline hash-check + score computation logic.

Cache invalidation note (PLAN-F-003 Risks):
  GeoWeightCalculator queries active events via ``get_recent_events`` (cache-
  first, P-02). For geo_weight to reflect a newly ingested event within the
  same Mode A session, the event pipeline step preceding step 7 must invalidate
  or bypass the geo-events cache entry after writing the new event.  This is a
  shared contract with the event-write step — document and enforce in the event
  pipeline owner's scope.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


def _compute_inputs_hash(
    portfolio_holdings: dict,
    category: str,
    intensity: int,
    tickers: list[str],
) -> str:
    """Compute a deterministic SHA-256 hash of the exposure scoring inputs.

    Used to detect when scores can be reused without recomputation (P-03).
    """
    payload = {
        "holdings": portfolio_holdings,
        "category": category,
        "intensity": intensity,
        "tickers": sorted(tickers),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _compute_exposure_score(
    portfolio_holdings: dict,
    event_tickers: set[str],
    intensity: int,
) -> float:
    """Compute weighted exposure score.

    Score = sum of holding weights for tickers affected by the event,
    multiplied by the normalised intensity (intensity / 5).
    """
    intensity_factor = intensity / 5.0
    affected_weight = sum(
        weight for ticker, weight in portfolio_holdings.items()
        if ticker in event_tickers
    )
    return round(affected_weight * intensity_factor, 4)


class ExposureScoreStep:
    """Pipeline Step 7: EXPOSURE SCORE.

    For each portfolio in state.exposure_map, computes an exposure score
    using inputs_hash invalidation (P-03). If the hash matches an existing
    record the cached score is reused; otherwise a new record is written.

    When ``scoring_engine`` is provided (TASK-014), it delegates to
    ``ScoringEngine.recompute_if_stale`` which handles the full
    hash-check → DSL eval → geo_weight → persist pipeline.

    Parameters
    ----------
    repo:
        Repository exposing:
          - ``get_portfolio_holdings(portfolio_id) -> dict``
          - ``get_event_score_by_hash(portfolio_id, event_id, inputs_hash) -> float | None``
          - ``write_event_score(portfolio_id, event_id, score, inputs_hash, ...)``
    scoring_engine:
        Optional ``ScoringEngine`` (ConcreteScoringPipeline). When provided,
        recomputation is fully delegated to it (TASK-014 wiring, AC-001,
        AC-004). When None, the legacy inline scoring path is used.
    indicator_version_id:
        The current indicator version UUID passed to ``scoring_engine``
        for provenance tracking (AC-005). Required when scoring_engine is set.
    dsl_expression:
        The DSL expression string evaluated by ``scoring_engine``.
        Required when scoring_engine is set.
    """

    step_name: str = "s07_exposure_score"

    def __init__(
        self,
        repo: Any,
        scoring_engine: Any | None = None,
        indicator_version_id: uuid.UUID | None = None,
        dsl_expression: str = "1",
    ) -> None:
        self._repo = repo
        self._scoring_engine = scoring_engine
        self._indicator_version_id = indicator_version_id or uuid.uuid4()
        self._dsl_expression = dsl_expression

    async def execute(self, state: PipelineState) -> PipelineState:
        """Compute or reuse exposure scores for all affected portfolios."""
        if self._scoring_engine is not None:
            return await self._execute_with_scoring_engine(state)
        return await self._execute_legacy(state)

    # ------------------------------------------------------------------
    # TASK-014: delegate to ConcreteScoringPipeline (preferred path)
    # ------------------------------------------------------------------

    async def _execute_with_scoring_engine(self, state: PipelineState) -> PipelineState:
        """Delegate recomputation to the injected ScoringEngine.

        For each portfolio holding affected by the event, builds an
        InputSnapshot from the event's company/portfolio data and calls
        ``scoring_engine.recompute_if_stale()``.  If the engine returns
        ``None`` (hash unchanged, AC-001) the exposure map entry is preserved
        at its prior value; if a new ScoreResult is returned the entry is
        updated with the new score.
        """
        from src.scoring.interfaces import InputSnapshot

        updated_map: dict[str, float] = dict(state.exposure_map)
        event_tickers = set(state.tickers)
        category_val = state.category.value if state.category else ""
        intensity = state.intensity or 1

        for portfolio_id_str in state.exposure_map:
            portfolio_id = uuid.UUID(portfolio_id_str)
            holdings: dict = await self._repo.get_portfolio_holdings(portfolio_id)

            # Build InputSnapshot from event data for this portfolio
            raw_inputs: dict[str, float | int | str] = {
                "intensity": float(intensity),
                "category": category_val,
            }
            for ticker, weight in holdings.items():
                if ticker in event_tickers:
                    raw_inputs[f"holding_{ticker}"] = float(weight)

            snapshot = InputSnapshot(
                company_id=portfolio_id,    # portfolio_id used as company_id in this context
                indicator_id=state.raw_event_id,
                raw_inputs=raw_inputs,
            )

            result = await self._scoring_engine.recompute_if_stale(
                snapshot=snapshot,
                indicator_version_id=self._indicator_version_id,
                dsl_expression=self._dsl_expression,
                tenant_id=state.tenant_id,
            )

            if result is not None:
                # Hash changed → new score computed and persisted
                updated_map[portfolio_id_str] = result.score
                logger.info(
                    "Step 7 (scoring engine): score=%.4f portfolio=%s hash=%s",
                    result.score,
                    portfolio_id_str,
                    result.inputs_hash,
                )
            else:
                # Hash unchanged — keep existing score
                logger.debug(
                    "Step 7 (scoring engine): hash unchanged, skipping portfolio=%s",
                    portfolio_id_str,
                )

        return state.model_copy(update={"exposure_map": updated_map})

    # ------------------------------------------------------------------
    # Legacy path (used when scoring_engine is not injected)
    # ------------------------------------------------------------------

    async def _execute_legacy(self, state: PipelineState) -> PipelineState:
        """Original inline scoring logic — preserved for backward compatibility."""
        updated_map: dict[str, float] = {}
        event_tickers = set(state.tickers)
        category_val = state.category.value if state.category else ""
        intensity = state.intensity or 1

        for portfolio_id_str in state.exposure_map:
            portfolio_id = uuid.UUID(portfolio_id_str)
            holdings = await self._repo.get_portfolio_holdings(portfolio_id)

            inputs_hash = _compute_inputs_hash(
                holdings, category_val, intensity, list(event_tickers)
            )

            # Check for cached score (P-03)
            cached = await self._repo.get_event_score_by_hash(
                portfolio_id=portfolio_id,
                event_id=state.raw_event_id,
                inputs_hash=inputs_hash,
            )

            if cached is not None:
                logger.debug(
                    "Step 7: reusing cached score portfolio=%s hash=%s",
                    portfolio_id_str,
                    inputs_hash,
                )
                updated_map[portfolio_id_str] = cached
            else:
                score = _compute_exposure_score(holdings, event_tickers, intensity)
                await self._repo.write_event_score(
                    portfolio_id=portfolio_id,
                    event_id=state.raw_event_id,
                    tenant_id=state.tenant_id,
                    score=score,
                    inputs_hash=inputs_hash,
                )
                updated_map[portfolio_id_str] = score
                logger.info(
                    "Step 7 (legacy): computed score=%.4f portfolio=%s",
                    score,
                    portfolio_id_str,
                )

        return state.model_copy(update={"exposure_map": updated_map})
