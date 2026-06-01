"""Scoring engine module — Portfolio & Company Scoring Engine (PLAN-F-003).

Public surface
--------------
Interfaces (Protocols + Pydantic models):
    InputSnapshot, ScoreResult, ScoreQuery
    HashEngine, DslEvaluator, GeoWeightCalculator, ScoreRepository, ScoringEngine

Concrete implementations:
    ConcreteHashEngine       — SHA-256 inputs_hash with float-normalisation
    ConcreteDslEvaluator     — Recursive AST interpreter
    ConcreteGeoWeightCalculator
    ConcreteScoreRepository  — SQLAlchemy 2 async, append-only
    ConcreteScoringPipeline  — Full orchestration pipeline

Exceptions:
    DslParseError, DslEvalError, HashMismatchNotice, InsufficientDataError

Dependency chain (top → bottom, no upward imports):
    src/event_pipeline/  → calls ConcreteScoringPipeline
    src/workflows/tools/ → calls ConcreteScoreRepository via GetEventExposureScoreTool
    src/scoring/         ← THIS MODULE
    src/providers/       ← raw data via typed Protocols
    src/markets/         ← MarketConfig registry
    src/db/              ← score_records ORM models
"""
from src.scoring.interfaces import (
    InputSnapshot,
    ScoreResult,
    ScoreQuery,
    HashEngine,
    DslEvaluator,
    GeoWeightCalculator,
    ScoreRepository,
    ScoringEngine,
)
from src.scoring.exceptions import (
    DslParseError,
    DslEvalError,
    HashMismatchNotice,
    InsufficientDataError,
)
from src.scoring.hash_engine import ConcreteHashEngine
from src.scoring.geo_weight import ConcreteGeoWeightCalculator
from src.scoring.repository import ConcreteScoreRepository
from src.scoring.pipeline import ConcreteScoringPipeline
from src.scoring.dsl.evaluator import ConcreteDslEvaluator

__all__ = [
    # Protocols + Pydantic models
    "InputSnapshot",
    "ScoreResult",
    "ScoreQuery",
    "HashEngine",
    "DslEvaluator",
    "GeoWeightCalculator",
    "ScoreRepository",
    "ScoringEngine",
    # Exceptions
    "DslParseError",
    "DslEvalError",
    "HashMismatchNotice",
    "InsufficientDataError",
    # Concrete implementations
    "ConcreteHashEngine",
    "ConcreteDslEvaluator",
    "ConcreteGeoWeightCalculator",
    "ConcreteScoreRepository",
    "ConcreteScoringPipeline",
]
