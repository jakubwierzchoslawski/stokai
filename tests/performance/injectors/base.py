"""EventInjector Protocol — abstract base for test event builders.

PLAN-N-001 TASK-001 — Interfaces and Contracts.

SOLID design:
  OCP: adding a new source type (e.g. PRICE_ANOMALY) requires only a new
       EventInjector subclass — zero changes to LatencyCollector or
       PerformanceReporter.
  DIP: LatencyCollector depends on this abstraction, not concrete adapters.
  ISP: minimal interface — only source_type and build_payload are required.

The Protocol uses runtime_checkable so isinstance() checks work in tests.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.event_pipeline.pipeline_state import RawEventPayload


@runtime_checkable
class EventInjector(Protocol):
    """Protocol defining the contract for all test event injectors.

    Each concrete injector builds ``RawEventPayload`` instances calibrated
    to a specific ingestion source.  The ``index`` parameter ensures that
    each invocation produces a payload with a unique fingerprint so that the
    pipeline deduplication step does not collapse the test run.

    Attributes
    ----------
    source_type:
        String matching a ``RawEventSource`` enum value (e.g. "GDELT").
    """

    source_type: str

    def build_payload(self, index: int) -> RawEventPayload:
        """Build a ``RawEventPayload`` for the given run index.

        Parameters
        ----------
        index:
            Zero-based run counter.  Must be embedded in the payload content
            and ID to guarantee uniqueness across 100+ sequential injections.

        Returns
        -------
        RawEventPayload:
            A fully-populated payload ready to pass to ``PipelineExecutor.run``.
        """
        ...
