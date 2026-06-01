"""ConcreteScoringPipeline — scoring orchestrator (PLAN-F-003 TASK-010 + TASK-011).

Implements the ``ScoringEngine`` Protocol. Orchestrates the full
hash-check → DSL eval → geo_weight → persist flow.

Algorithm (``recompute_if_stale``):
    1. Validate company's market is active (if market_registry provided).
    2. Compute fresh hash via HashEngine.
    3. Retrieve stored hash from ScoreRepository.
    4. If hash unchanged → return None (AC-001 no-op invariant).
    5. Build context dict from snapshot.raw_inputs.
    6. Evaluate DSL expression → dsl_score.
    7. Calculate geo_weight.
    8. Compute final_score = dsl_score * geo_weight.
    9. Build ScoreResult with full provenance.
    10. Persist via ScoreRepository.append().
    11. Return ScoreResult.

Dependencies are injected at construction time (DIP). No concrete
collaborator is instantiated inside this class.

TASK-011 extension: optional ``market_registry`` and ``company_market_id``
parameters enable market-active validation (AC-003). When no registry is
provided the pipeline operates without market-level checks (backward-compat).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.markets.config import MarketRegistry
from src.scoring.interfaces import (
    DslEvaluator,
    GeoWeightCalculator,
    HashEngine,
    InputSnapshot,
    ScoreRepository,
    ScoreResult,
)


class ConcreteScoringPipeline:
    """Orchestrates hash-check → DSL eval → geo_weight → persist.

    Parameters
    ----------
    hash_engine:
        Injected ``HashEngine`` — computes and compares inputs_hash.
    dsl_evaluator:
        Injected ``DslEvaluator`` — evaluates the DSL expression.
    geo_weight_calculator:
        Injected ``GeoWeightCalculator`` — computes the geo_weight multiplier.
    score_repository:
        Injected ``ScoreRepository`` — persists and reads score records.
    market_registry:
        Optional injected ``MarketRegistry``.  When provided, the pipeline
        validates that the company's market is ``enabled=True`` before scoring
        (TASK-011, AC-003).
    company_market_id:
        The market_id string for the company being scored.  Used together
        with ``market_registry`` for market-active validation.
    """

    def __init__(
        self,
        hash_engine: HashEngine,
        dsl_evaluator: DslEvaluator,
        geo_weight_calculator: GeoWeightCalculator,
        score_repository: ScoreRepository,
        market_registry: MarketRegistry | None = None,
        company_market_id: str = "",
    ) -> None:
        self._hash_engine = hash_engine
        self._dsl_evaluator = dsl_evaluator
        self._geo_weight_calculator = geo_weight_calculator
        self._score_repository = score_repository
        self._market_registry = market_registry
        self._company_market_id = company_market_id

    async def recompute_if_stale(
        self,
        snapshot: InputSnapshot,
        indicator_version_id: uuid.UUID,
        dsl_expression: str,
        tenant_id: uuid.UUID,
    ) -> ScoreResult | None:
        """Recompute the score for *snapshot* if its inputs_hash has changed.

        Returns
        -------
        ScoreResult
            The newly computed and persisted score when the hash changed.
        None
            When the hash is unchanged — no recomputation performed (AC-001).

        Raises
        ------
        ValueError
            When the company's market is inactive (only if market_registry
            and company_market_id are provided).
        """
        # Step 1: validate market is active (TASK-011)
        self._validate_market_active()

        # Step 2: compute fresh hash
        new_hash = self._hash_engine.compute(snapshot)

        # Step 3: retrieve stored hash
        stored_hash = await self._score_repository.get_stored_hash(
            company_id=snapshot.company_id,
            indicator_id=snapshot.indicator_id,
            tenant_id=tenant_id,
        )

        # Step 4: hash unchanged → no-op
        if not self._hash_engine.has_changed(snapshot, stored_hash or ""):
            return None

        # Step 5: build context from raw_inputs (convert numeric values to float)
        context: dict[str, float] = {
            k: float(v)
            for k, v in snapshot.raw_inputs.items()
            if isinstance(v, (int, float))
        }
        # String values participate in hash computation but not in DSL evaluation

        # Step 6: evaluate DSL → dsl_score (propagates DslParseError / DslEvalError)
        dsl_score = self._dsl_evaluator.evaluate(dsl_expression, context)

        # Step 7: calculate geo_weight
        geo_weight = self._geo_weight_calculator.calculate(
            company_id=snapshot.company_id,
            tenant_id=tenant_id,
        )

        # Step 8: final score = dsl_score × geo_weight
        final_score = dsl_score * geo_weight

        # Step 9: build ScoreResult with full provenance (AC-005)
        result = ScoreResult(
            score_id=uuid.uuid4(),
            company_id=snapshot.company_id,
            indicator_id=snapshot.indicator_id,
            indicator_version_id=indicator_version_id,
            score=final_score,
            geo_weight_applied=geo_weight,
            inputs_hash=new_hash,
            computed_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )

        # Step 10: persist
        await self._score_repository.append(result)

        # Step 11: return result
        return result

    def _validate_market_active(self) -> None:
        """Raise ValueError if the company's market is not active.

        No-op when no market_registry is configured (backward-compatible).
        """
        if self._market_registry is None or not self._company_market_id:
            return

        config = self._market_registry.get_market_config(self._company_market_id)
        if config is not None and not config.enabled:
            raise ValueError(
                f"Market {self._company_market_id!r} is inactive. "
                "Enable the market in the MarketRegistry before scoring."
            )
