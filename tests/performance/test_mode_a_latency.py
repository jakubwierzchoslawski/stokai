"""
Mode A Reactive Pipeline — Latency SLA assertions.

PLAN-N-001 TASK-003 (test suite) and TASK-005 (baseline documentation).

SLA targets (ARCHITECTURE.md §6 Latency Budget and §14 NFR Summary):
  Tweet / X_FILTERED_STREAM : p95 detected_at → dispatched_at < 30 seconds
  GDELT geo-events          : p95 detected_at → dispatched_at < 90 seconds
  SEC EDGAR filings         : p95 detected_at → dispatched_at < 1 200 seconds (20 minutes)

Test event counts:
  Tweet  : 100 sequential events
  GDELT  : 100 sequential events
  EDGAR  : 20 sequential events  (generous SLA makes 20 a stable p95 sample)

Infrastructure assumptions (mock-LLM conditions):
  - LLM calls are replaced with MockLLMClassifier (< 5ms per call).
  - Real PostgreSQL and Redis infrastructure used via performance_db_session fixture.
  - Redis keys are namespaced to 'perf:{test_run_id}:*' to prevent cross-contamination.
  - Mock LLM confidence is fixed at 0.85 (>= 0.7) forcing AUTO_SEND routing so that
    true dispatched_at proxy values (generated_at from TraceStep) are produced.

Architectural reference:
  ARCHITECTURE.md §6 Mode A Reactive Pipeline — Latency Budget
  ARCHITECTURE.md §14 NFR Summary — Latency row

IMPORTANT — Scope of these tests:
  These tests measure INFRASTRUCTURE latency under mock-LLM conditions.
  The measurements provide a lower-bound on real end-to-end latency.
  Before production sign-off, a manual run with real Haiku 4.5 LLM calls
  is REQUIRED to verify SLAs hold end-to-end.
  Real Haiku 4.5 p99 classify latency is typically 1–3 seconds per call;
  with two LLM calls per event (classify + confidence), the real-call budget
  for all other steps is approximately 24 seconds for the tweet SLA.

All tests in this module are tagged @pytest.mark.performance and are excluded
from the default test suite (run with: pytest -m performance).
CI performance-gate stage: pytest tests/performance/ -m performance --tb=short -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest


# ---------------------------------------------------------------------------
# test_tweet_p95_under_30s
# ---------------------------------------------------------------------------

@pytest.mark.performance
async def test_tweet_p95_under_30s(pipeline_executor_factory) -> None:
    """100 tweet-class events: p95 detected_at → dispatched_at < 30 seconds.

    AC-001: 100 sequential X_FILTERED_STREAM test events processed.
    p95 of elapsed seconds from detected_at to dispatched_at proxy must be < 30.0.

    Failure message includes actual p95, p99, and max values for diagnosis.
    Langfuse trace spans (written by TraceStep) provide per-step breakdown
    if the SLA is breached.
    """
    from tests.performance.collectors.latency_collector import LatencyCollector
    from tests.performance.collectors.performance_reporter import PerformanceReporter
    from tests.performance.injectors.tweet_injector import TweetEventInjector

    executor = pipeline_executor_factory()
    injector = TweetEventInjector()

    collector = LatencyCollector(
        executor=executor,
        db_session=None,
        injector=injector,
    )

    durations: list[float] = []
    for i in range(100):
        elapsed = await collector.run_once(i)
        durations.append(elapsed)

    report = PerformanceReporter.compute(durations)

    assert report.p95 < 30.0, (
        f"Tweet SLA BREACH — AC-001 FAILED\n"
        f"  p95={report.p95:.3f}s (threshold: < 30.0s)\n"
        f"  p99={report.p99:.3f}s\n"
        f"  max={report.max:.3f}s\n"
        f"  sample_count={report.sample_count}\n"
        f"  Check Langfuse trace spans for per-step latency breakdown."
    )


# ---------------------------------------------------------------------------
# test_gdelt_p95_under_90s
# ---------------------------------------------------------------------------

@pytest.mark.performance
async def test_gdelt_p95_under_90s(pipeline_executor_factory) -> None:
    """100 GDELT geo-events: p95 detected_at → dispatched_at < 90 seconds.

    AC-002: 100 sequential GDELT test events processed.
    p95 of elapsed seconds from detected_at to dispatched_at proxy must be < 90.0.
    """
    from tests.performance.collectors.latency_collector import LatencyCollector
    from tests.performance.collectors.performance_reporter import PerformanceReporter
    from tests.performance.injectors.gdelt_injector import GdeltEventInjector

    executor = pipeline_executor_factory()
    injector = GdeltEventInjector()

    collector = LatencyCollector(
        executor=executor,
        db_session=None,
        injector=injector,
    )

    durations: list[float] = []
    for i in range(100):
        elapsed = await collector.run_once(i)
        durations.append(elapsed)

    report = PerformanceReporter.compute(durations)

    assert report.p95 < 90.0, (
        f"GDELT SLA BREACH — AC-002 FAILED\n"
        f"  p95={report.p95:.3f}s (threshold: < 90.0s)\n"
        f"  p99={report.p99:.3f}s\n"
        f"  max={report.max:.3f}s\n"
        f"  sample_count={report.sample_count}\n"
        f"  Check Langfuse trace spans for per-step latency breakdown."
    )


# ---------------------------------------------------------------------------
# test_edgar_p95_under_20_minutes
# ---------------------------------------------------------------------------

@pytest.mark.performance
async def test_edgar_p95_under_20_minutes(pipeline_executor_factory) -> None:
    """20 SEC EDGAR filing events: p95 detected_at → dispatched_at < 1 200 seconds.

    AC-003: 20 sequential SEC_EDGAR test events processed.
    p95 of elapsed seconds from detected_at to dispatched_at proxy must be < 1200.0
    (20 minutes).

    Note: twenty events is a small sample for a stable p95 estimate.  The EDGAR
    SLA of 20 minutes is generous enough that one outlier at the top is still a
    meaningful signal.  Raise to 50 events if flakiness is observed.
    """
    from tests.performance.collectors.latency_collector import LatencyCollector
    from tests.performance.collectors.performance_reporter import PerformanceReporter
    from tests.performance.injectors.edgar_injector import EdgarEventInjector

    executor = pipeline_executor_factory()
    injector = EdgarEventInjector()

    collector = LatencyCollector(
        executor=executor,
        db_session=None,
        injector=injector,
    )

    durations: list[float] = []
    for i in range(20):
        elapsed = await collector.run_once(i)
        durations.append(elapsed)

    report = PerformanceReporter.compute(durations)

    assert report.p95 < 1200.0, (
        f"EDGAR SLA BREACH — AC-003 FAILED\n"
        f"  p95={report.p95:.3f}s (threshold: < 1200.0s / 20 minutes)\n"
        f"  p99={report.p99:.3f}s\n"
        f"  max={report.max:.3f}s\n"
        f"  sample_count={report.sample_count}\n"
        f"  Check Langfuse trace spans for per-step latency breakdown."
    )


# ---------------------------------------------------------------------------
# test_event_record_timestamps_non_null
# ---------------------------------------------------------------------------

@pytest.mark.performance
async def test_event_record_timestamps_non_null(pipeline_executor_factory) -> None:
    """One pipeline run per source type: detected_at and generated_at are non-null.

    AC-004: For each source type (tweet, GDELT, EDGAR), a completed pipeline
    run must produce a PipelineState (and proxied EventRecord) with:
      - detected_at is not None
      - generated_at is not None

    This test does not assert latency thresholds — it is a data-integrity
    assertion that covers AC-004 independently of p95 calculations.
    """
    from tests.performance.collectors.latency_collector import LatencyCollector
    from tests.performance.injectors.tweet_injector import TweetEventInjector
    from tests.performance.injectors.gdelt_injector import GdeltEventInjector
    from tests.performance.injectors.edgar_injector import EdgarEventInjector
    from src.event_pipeline.pipeline_state import PipelineState, RawEventPayload

    source_injectors = [
        ("X_FILTERED_STREAM", TweetEventInjector()),
        ("GDELT", GdeltEventInjector()),
        ("SEC_EDGAR", EdgarEventInjector()),
    ]

    for source_name, injector in source_injectors:
        executor = pipeline_executor_factory()
        collector = LatencyCollector(
            executor=executor,
            db_session=None,
            injector=injector,
        )

        # Run once to get the final state
        payload = injector.build_payload(0)
        import uuid as _uuid
        raw_event_id = _uuid.uuid4()
        initial_state = PipelineState(
            raw_event_id=raw_event_id,
            tenant_id=payload.tenant_id,
            payload=payload,
        )
        final_state: PipelineState = await executor.run(initial_state)

        # AC-004: detected_at must be set on the payload (injector sets it)
        assert final_state.payload.detected_at is not None, (
            f"AC-004 FAILED for source={source_name}: "
            f"payload.detected_at is None"
        )

        # AC-004: generated_at must be set by TraceStep (Step 13)
        assert final_state.generated_at is not None, (
            f"AC-004 FAILED for source={source_name}: "
            f"generated_at is None after pipeline completion. "
            f"TraceStep (Step 13) must set generated_at on every successful run."
        )
