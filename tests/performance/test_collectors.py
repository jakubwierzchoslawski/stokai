"""TDD tests for LatencyCollector and PerformanceReporter.

Tests written FIRST (TDD red phase) for PLAN-N-001 TASK-002.

Tests:
    test_collector_run_once_returns_positive_float
    test_collector_raises_if_detected_at_null
    test_collector_raises_if_dispatched_at_null
    test_reporter_p95_of_known_sequence
    test_reporter_raises_on_empty_list
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any


class TestLatencyCollector:
    """Tests for LatencyCollector.run_once().

    PLAN-N-001 TASK-002.
    """

    async def test_collector_run_once_returns_positive_float(self) -> None:
        """Single pipeline run with mock executor; assert return value is a positive float."""
        from tests.performance.collectors.latency_collector import LatencyCollector
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        # Build a mock executor that returns a completed state
        detected_at = datetime.now(timezone.utc)
        dispatched_at = detected_at + timedelta(seconds=5.0)

        # Mock the EventRecord and AlertRecord rows
        mock_event_record = MagicMock()
        mock_event_record.detected_at = detected_at
        mock_event_record.generated_at = detected_at + timedelta(seconds=4.5)

        mock_alert_record = MagicMock()
        mock_alert_record.dispatched_at = dispatched_at

        # Mock the DB session that will return these records
        mock_session = AsyncMock()

        # Mock the pipeline state returned by executor.run()
        from src.event_pipeline.pipeline_state import (
            PipelineState,
            RawEventPayload,
            RawEventSource,
            AlertRoute,
        )
        initial_payload = RawEventPayload(
            source=RawEventSource.X_FILTERED_STREAM,
            raw_payload={"text": "test"},
            detected_at=detected_at,
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )
        initial_state = PipelineState(
            raw_event_id=uuid.uuid4(),
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            payload=initial_payload,
            generated_at=detected_at + timedelta(seconds=4.5),
            route=AlertRoute.AUTO_SEND,
            confidence=0.85,
        )
        final_state = initial_state.model_copy(update={"generated_at": detected_at + timedelta(seconds=4.5)})

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=final_state)

        injector = TweetEventInjector()

        collector = LatencyCollector(
            executor=mock_executor,
            db_session=mock_session,
            injector=injector,
        )

        # Patch the DB queries that LatencyCollector uses to fetch records
        with (
            patch.object(
                collector,
                "_fetch_event_record",
                new=AsyncMock(return_value=mock_event_record),
            ),
            patch.object(
                collector,
                "_fetch_alert_record",
                new=AsyncMock(return_value=mock_alert_record),
            ),
            patch.object(
                collector,
                "_persist_raw_event",
                new=AsyncMock(return_value=initial_state.raw_event_id),
            ),
        ):
            result = await collector.run_once(0)

        assert isinstance(result, float), f"Expected float, got {type(result)}"
        assert result > 0.0, f"Expected positive elapsed seconds, got {result}"

    async def test_collector_raises_if_detected_at_null(self) -> None:
        """Mock EventRecord with detected_at=None; assert AssertionError raised."""
        from tests.performance.collectors.latency_collector import LatencyCollector
        from tests.performance.injectors.tweet_injector import TweetEventInjector
        import pytest

        detected_at = datetime.now(timezone.utc)

        # EventRecord with detected_at=None (corrupt state)
        mock_event_record = MagicMock()
        mock_event_record.detected_at = None
        mock_event_record.generated_at = detected_at

        mock_alert_record = MagicMock()
        mock_alert_record.dispatched_at = detected_at + timedelta(seconds=5.0)

        mock_session = AsyncMock()

        from src.event_pipeline.pipeline_state import (
            PipelineState,
            RawEventPayload,
            RawEventSource,
            AlertRoute,
        )
        initial_payload = RawEventPayload(
            source=RawEventSource.X_FILTERED_STREAM,
            raw_payload={"text": "test"},
            detected_at=detected_at,
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )
        initial_state = PipelineState(
            raw_event_id=uuid.uuid4(),
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            payload=initial_payload,
            route=AlertRoute.AUTO_SEND,
            confidence=0.85,
        )

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=initial_state)

        injector = TweetEventInjector()
        collector = LatencyCollector(
            executor=mock_executor,
            db_session=mock_session,
            injector=injector,
        )

        with (
            patch.object(
                collector,
                "_fetch_event_record",
                new=AsyncMock(return_value=mock_event_record),
            ),
            patch.object(
                collector,
                "_fetch_alert_record",
                new=AsyncMock(return_value=mock_alert_record),
            ),
            patch.object(
                collector,
                "_persist_raw_event",
                new=AsyncMock(return_value=initial_state.raw_event_id),
            ),
        ):
            with pytest.raises(AssertionError, match="detected_at"):
                await collector.run_once(0)

    async def test_collector_raises_if_dispatched_at_null(self) -> None:
        """Mock AlertRecord with dispatched_at=None; assert AssertionError raised."""
        from tests.performance.collectors.latency_collector import LatencyCollector
        from tests.performance.injectors.tweet_injector import TweetEventInjector
        import pytest

        detected_at = datetime.now(timezone.utc)

        mock_event_record = MagicMock()
        mock_event_record.detected_at = detected_at
        mock_event_record.generated_at = detected_at + timedelta(seconds=4.5)

        # AlertRecord with dispatched_at=None
        mock_alert_record = MagicMock()
        mock_alert_record.dispatched_at = None

        mock_session = AsyncMock()

        from src.event_pipeline.pipeline_state import (
            PipelineState,
            RawEventPayload,
            RawEventSource,
            AlertRoute,
        )
        initial_payload = RawEventPayload(
            source=RawEventSource.X_FILTERED_STREAM,
            raw_payload={"text": "test"},
            detected_at=detected_at,
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )
        initial_state = PipelineState(
            raw_event_id=uuid.uuid4(),
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            payload=initial_payload,
            route=AlertRoute.AUTO_SEND,
            confidence=0.85,
        )

        mock_executor = AsyncMock()
        mock_executor.run = AsyncMock(return_value=initial_state)

        injector = TweetEventInjector()
        collector = LatencyCollector(
            executor=mock_executor,
            db_session=mock_session,
            injector=injector,
        )

        with (
            patch.object(
                collector,
                "_fetch_event_record",
                new=AsyncMock(return_value=mock_event_record),
            ),
            patch.object(
                collector,
                "_fetch_alert_record",
                new=AsyncMock(return_value=mock_alert_record),
            ),
            patch.object(
                collector,
                "_persist_raw_event",
                new=AsyncMock(return_value=initial_state.raw_event_id),
            ),
        ):
            with pytest.raises(AssertionError, match="dispatched_at"):
                await collector.run_once(0)

    def test_collector_is_dataclass(self) -> None:
        """LatencyCollector must be a dataclass with executor, db_session, injector."""
        from tests.performance.collectors.latency_collector import LatencyCollector
        import dataclasses

        fields = {f.name for f in dataclasses.fields(LatencyCollector)}
        assert "executor" in fields
        assert "db_session" in fields
        assert "injector" in fields


class TestPerformanceReporter:
    """Tests for PerformanceReporter.compute().

    PLAN-N-001 TASK-002.
    """

    def test_reporter_p95_of_known_sequence(self) -> None:
        """Feed [1.0] * 95 + [100.0] * 5; assert p95 == 100.0 and p50 == 1.0."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter

        durations = [1.0] * 95 + [100.0] * 5
        report = PerformanceReporter.compute(durations)

        assert report.p95 == 100.0, f"Expected p95=100.0, got {report.p95}"
        assert report.p50 == 1.0, f"Expected p50=1.0, got {report.p50}"
        assert report.sample_count == 100

    def test_reporter_raises_on_empty_list(self) -> None:
        """PerformanceReporter.compute([]) must raise ValueError."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter
        import pytest

        with pytest.raises(ValueError, match="empty"):
            PerformanceReporter.compute([])

    def test_reporter_single_value(self) -> None:
        """Single-value list must return equal p50/p95/p99/max."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter

        report = PerformanceReporter.compute([42.0])
        assert report.p50 == 42.0
        assert report.p95 == 42.0
        assert report.p99 == 42.0
        assert report.max == 42.0
        assert report.sample_count == 1

    def test_reporter_max_is_largest_value(self) -> None:
        """max field must be the largest value in the input list."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter

        durations = [1.0, 2.0, 3.0, 50.0, 0.5]
        report = PerformanceReporter.compute(durations)
        assert report.max == 50.0

    def test_reporter_returns_latency_report_dataclass(self) -> None:
        """compute() must return a LatencyReport dataclass."""
        from tests.performance.collectors.performance_reporter import (
            PerformanceReporter,
            LatencyReport,
        )
        import dataclasses

        report = PerformanceReporter.compute([1.0, 2.0, 3.0])
        assert isinstance(report, LatencyReport)
        assert dataclasses.is_dataclass(report)

    def test_reporter_is_pure_no_side_effects(self) -> None:
        """PerformanceReporter.compute must not mutate the input list."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter

        durations = [5.0, 1.0, 3.0, 2.0, 4.0]
        original = durations.copy()
        PerformanceReporter.compute(durations)
        assert durations == original, "compute() must not mutate the input list"

    def test_reporter_all_percentiles_ordered(self) -> None:
        """p50 <= p95 <= p99 <= max must always hold."""
        from tests.performance.collectors.performance_reporter import PerformanceReporter

        durations = list(range(1, 101))  # 1..100
        report = PerformanceReporter.compute([float(d) for d in durations])
        assert report.p50 <= report.p95, f"p50={report.p50} > p95={report.p95}"
        assert report.p95 <= report.p99, f"p95={report.p95} > p99={report.p99}"
        assert report.p99 <= report.max, f"p99={report.p99} > max={report.max}"
