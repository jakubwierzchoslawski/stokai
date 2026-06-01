"""TDD tests for performance conftest fixtures.

Tests written FIRST (TDD red phase) for PLAN-N-001 TASK-001.
Validates that performance fixtures are correctly wired.

Tests:
    test_lm_mock_returns_in_under_5ms
"""
from __future__ import annotations

import time
import uuid


class TestLLMMockPerformance:
    """Verify LLM mock latency is under 5ms per call.

    PLAN-N-001 TASK-001: mock LLM calls must be calibrated to return in
    < 5 ms to isolate infrastructure latency rather than artificial LLM latency.
    """

    def test_lm_mock_returns_in_under_5ms(self) -> None:
        """Time the mock LLM call; assert it completes in < 5 ms."""
        from tests.performance.conftest import MockLLMClassifier

        mock = MockLLMClassifier()
        start = time.perf_counter()
        result = mock.classify_sync("Test event text for performance measurement")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5.0, (
            f"Mock LLM call took {elapsed_ms:.2f}ms, must be < 5ms"
        )
        assert result is not None, "Mock LLM classifier must return a non-None result"

    def test_lm_mock_returns_fixed_category(self) -> None:
        """Mock classifier must return a fixed, deterministic category."""
        from tests.performance.conftest import MockLLMClassifier

        mock = MockLLMClassifier()
        result1 = mock.classify_sync("event text A")
        result2 = mock.classify_sync("event text B")

        assert result1["category"] == result2["category"], (
            "Mock LLM must return deterministic category regardless of input"
        )

    async def test_lm_mock_returns_high_confidence(self) -> None:
        """Mock confidence must be >= 0.7 to force AUTO_SEND routing.

        Confidence comes from synthesise_confidence (Step 9), not classify (Step 4).
        The mock must return >= 0.7 to produce AUTO_SEND routing and true
        dispatched_at values in latency tests.
        """
        from tests.performance.conftest import MockLLMClassifier, MOCK_CONFIDENCE

        assert MOCK_CONFIDENCE >= 0.7, (
            f"MOCK_CONFIDENCE {MOCK_CONFIDENCE} must be >= 0.7 to produce "
            "AUTO_SEND routing and true dispatched_at values in latency tests"
        )

        mock = MockLLMClassifier()
        confidence = await mock.synthesise_confidence("any event prompt")
        assert confidence >= 0.7, (
            f"MockLLMClassifier.synthesise_confidence returned {confidence}, "
            "must be >= 0.7"
        )
