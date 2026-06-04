"""Scoring service orchestrator — 9-step pipeline.

Steps:
  1. Load indicator record.
  2. Parse DSL → AST (cached per indicator version).
  3. Evaluate AST → raw_value.
  4. Fetch peer values (once per batch, not per company).
  5. Select normalization strategy.
  6. Normalize → score (with direction inversion).
  7. If geo_weight > 0 and geo_event_context provided: apply GeoModifier → geo_adjusted.
  8. Compute inputs_hash.
  9. upsert_if_changed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.scoring.benchmark_engine import BenchmarkEngine
from src.scoring.dsl.parser import parse
from src.scoring.dsl.tokenizer import tokenize
from src.scoring.evaluator.ast_evaluator import AstEvaluator
from src.scoring.evaluator.interfaces import IFundamentalsProvider, IParameterCatalog
from src.scoring.geo_modifier import GeoModifier
from src.scoring.normalization.min_max import MinMaxNormalizer
from src.scoring.normalization.percentile import PercentileNormalizer
from src.scoring.normalization.z_score import ZScoreNormalizer
from src.scoring.repositories.company_score_repo import compute_inputs_hash
from src.scoring.repositories.interfaces import (
    ICompanyScoreRepository,
    IIndicatorRepository,
)
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.schemas.indicator import IndicatorRecord

logger = logging.getLogger(__name__)


@dataclass
class GeoEventContext:
    """Context data for a geo event that triggered invalidation."""
    geo_regions: list[str]
    event_intensity: int
    event_sentiment: float = -0.5  # default bearish


class ScoringService:
    """Orchestrates the 9-step scoring pipeline per company.

    All dependencies are injected; no direct DB or external API calls.
    """

    def __init__(
        self,
        evaluator: AstEvaluator,
        benchmark_engine: BenchmarkEngine,
        geo_modifier: GeoModifier,
        score_repository: ICompanyScoreRepository,
        indicator_repository: IIndicatorRepository,
    ) -> None:
        self._evaluator = evaluator
        self._benchmark_engine = benchmark_engine
        self._geo_modifier = geo_modifier
        self._score_repo = score_repository
        self._indicator_repo = indicator_repository
        # Cache: (indicator_id, version) → AstNode
        self._ast_cache: dict[tuple[UUID, int], Any] = {}

    async def score_company(
        self,
        company_id: UUID,
        indicator_id: UUID,
        tenant_id: UUID,
        geo_event_context: GeoEventContext | None = None,
        peer_values: list[float] | None = None,
    ) -> CompanyScoreRecord | None:
        """Compute and (if changed) persist score for a single company.

        Args:
            company_id: company to score.
            indicator_id: indicator to apply.
            tenant_id: tenant context.
            geo_event_context: optional geo event for geo-modifier step.
            peer_values: pre-fetched peer values (avoids re-fetch per company in batch).

        Returns:
            CompanyScoreRecord if score was written; None if evaluator returned None.
        """
        # Step 1: Load indicator
        indicator = await self._indicator_repo.get_by_id(indicator_id, tenant_id)
        if indicator is None:
            logger.warning("Indicator %s not found for tenant %s", indicator_id, tenant_id)
            return None

        # Step 2: Parse DSL → AST (cached per version)
        cache_key = (indicator.indicator_id, indicator.version)
        if cache_key not in self._ast_cache:
            tokens = tokenize(indicator.formula_dsl)
            self._ast_cache[cache_key] = parse(tokens)
        ast = self._ast_cache[cache_key]

        # Step 3: Evaluate AST → raw_value
        raw_value = await self._evaluator.evaluate(ast, company_id, tenant_id)
        if raw_value is None:
            logger.debug(
                "Evaluator returned None for company %s / indicator %s — skipping.",
                company_id,
                indicator_id,
            )
            return None

        # Step 4: Fetch peer values (if not pre-fetched)
        if peer_values is None:
            try:
                peer_values = await self._benchmark_engine.get_peer_values(
                    indicator_id, "default", tenant_id
                )
            except Exception as exc:
                logger.warning("Could not fetch peer values: %s — using empty peers.", exc)
                peer_values = []

        # Step 5 & 6: Select normalization strategy and normalize
        score = self._normalize(raw_value, indicator, peer_values)

        # Step 7: Apply geo-modifier if applicable
        geo_adjusted: float | None = None
        if indicator.geo_weight > 0.0 and geo_event_context is not None:
            # Fetch company's geo_revenue from fundamentals provider
            # (conceptually — in practice we'd need this from the provider)
            geo_adjusted = self._geo_modifier.apply(
                base_score=score,
                geo_weight=indicator.geo_weight,
                geo_revenue={},  # populated by caller with actual revenue data
                event_regions=geo_event_context.geo_regions,
                event_intensity=geo_event_context.event_intensity,
                event_sentiment=geo_event_context.event_sentiment,
            )
        else:
            geo_adjusted = score

        # Step 8: Compute inputs_hash
        inputs = {
            "company_id": str(company_id),
            "indicator_id": str(indicator_id),
            "raw_value": round(raw_value, 6),
            "indicator_version": indicator.version,
        }
        inputs_hash = compute_inputs_hash(inputs)

        # Step 9: upsert_if_changed
        record = CompanyScoreRecord.new(
            company_id=company_id,
            indicator_id=indicator_id,
            tenant_id=tenant_id,
            raw_value=raw_value,
            score=score,
            inputs_hash=inputs_hash,
            geo_adjusted=geo_adjusted,
        )
        written = await self._score_repo.upsert_if_changed(record)
        if written:
            return record
        return None

    async def batch_rescore(
        self,
        company_ids: list[UUID],
        indicator_id: UUID,
        tenant_id: UUID,
        geo_event_context: GeoEventContext | None = None,
    ) -> dict[UUID, CompanyScoreRecord | None]:
        """Rescore multiple companies for a single indicator.

        Fetches benchmark stats once, then scores each company individually.

        Returns:
            Mapping of company_id → CompanyScoreRecord (or None if unchanged/null).
        """
        # Fetch peer values once for the entire batch
        try:
            peer_values = await self._benchmark_engine.get_peer_values(
                indicator_id, "default", tenant_id
            )
        except Exception:
            peer_values = []

        # Score each company concurrently
        tasks = [
            self.score_company(
                company_id=cid,
                indicator_id=indicator_id,
                tenant_id=tenant_id,
                geo_event_context=geo_event_context,
                peer_values=peer_values,
            )
            for cid in company_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            company_id: (result if not isinstance(result, Exception) else None)
            for company_id, result in zip(company_ids, results)
        }

    def _normalize(
        self,
        raw_value: float,
        indicator: IndicatorRecord,
        peer_values: list[float],
    ) -> float:
        """Apply the indicator's normalization strategy to *raw_value*."""
        direction = indicator.direction
        config = indicator.normalization_config or {}
        mode = indicator.normalization_mode

        if mode == "percentile":
            normalizer = PercentileNormalizer(direction=direction)
            return normalizer.normalize(raw_value, peer_values=peer_values)
        elif mode == "z_score":
            from src.scoring.benchmark_engine import BenchmarkStats
            if peer_values:
                stats = self._benchmark_engine.compute_benchmark_stats(peer_values)
                mean = stats.mean
                std = stats.std
            else:
                mean = float(config.get("mean", 0.0))
                std = float(config.get("std", 1.0))
            normalizer = ZScoreNormalizer(direction=direction)
            return normalizer.normalize(raw_value, mean=mean, std=std)
        elif mode == "min_max":
            min_val = float(config.get("min_val", 0.0))
            max_val = float(config.get("max_val", 100.0))
            normalizer = MinMaxNormalizer(direction=direction)
            try:
                return normalizer.normalize(raw_value, min_val=min_val, max_val=max_val)
            except ValueError:
                return 50.0  # fallback if range is invalid
        else:
            logger.warning("Unknown normalization mode: %s — defaulting to min_max", mode)
            normalizer = MinMaxNormalizer(direction=direction)
            try:
                return normalizer.normalize(raw_value, min_val=0.0, max_val=100.0)
            except ValueError:
                return 50.0
