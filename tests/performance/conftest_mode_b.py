"""
Shared fixtures and fakes for Mode B workflow latency tests (PLAN-N-002/TASK-006).

Provides:
  FakeWorkflowClock(elapsed_seconds)
    — Injectable clock that returns a fixed elapsed time so latency tests
      run in milliseconds (no real asyncio.sleep).

  build_fake_workflow_state(workflow_type, started_at)
    — Constructs a minimal WorkflowState for each workflow type.

  FakeWorkflowGraph(target_duration_seconds, raises_at_seconds=None)
    — Fake LangGraph graph; accepts a clock injection.
      If raises_at_seconds is set, raises SoftTimeLimitExceeded when
      the injected clock reaches that value.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


# ---------------------------------------------------------------------------
# FakeWorkflowClock
# ---------------------------------------------------------------------------


class FakeWorkflowClock:
    """Injectable clock returning a fixed elapsed_seconds value.

    Used to make latency tests deterministic and fast (no real sleep).

    Args:
        elapsed_seconds: The fixed elapsed time this clock always returns.
    """

    def __init__(self, elapsed_seconds: float) -> None:
        self.elapsed_seconds = elapsed_seconds

    def now(self) -> datetime:
        """Return the current UTC time (real wall clock for started_at anchor)."""
        return datetime.now(tz=timezone.utc)

    def elapsed_since(self, started_at: datetime) -> float:
        """Return the fixed elapsed_seconds regardless of started_at."""
        return self.elapsed_seconds


# ---------------------------------------------------------------------------
# build_fake_workflow_state
# ---------------------------------------------------------------------------


def build_fake_workflow_state(
    workflow_type: WorkflowType,
    started_at: datetime | None = None,
    **kwargs: Any,
) -> WorkflowState:
    """Build a minimal WorkflowState for the given workflow type.

    Args:
        workflow_type: The Mode B workflow type.
        started_at:    Optional override; defaults to utcnow().
        **kwargs:      Additional field overrides.

    Returns:
        A WorkflowState with sensible defaults for testing.
    """
    return WorkflowState(
        workflow_id=uuid4(),
        workflow_type=workflow_type,
        tenant_id=uuid4(),
        user_id=uuid4(),
        company_id=uuid4(),
        started_at=started_at or datetime.now(tz=timezone.utc),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# FakeWorkflowGraph
# ---------------------------------------------------------------------------


class FakeWorkflowGraph:
    """Fake LangGraph graph for testing.

    Simulates a workflow that takes target_duration_seconds to complete.
    Uses an injectable clock so tests run at wall speed.

    Args:
        target_duration_seconds: Simulated execution time (real asyncio.sleep).
        raises_at_seconds:       If set, raises SoftTimeLimitExceeded when
                                 the clock reports elapsed >= this value.
        use_real_sleep:          If False (default), returns instantly.
                                 If True, uses real asyncio.sleep.
    """

    def __init__(
        self,
        target_duration_seconds: float,
        raises_at_seconds: float | None = None,
        use_real_sleep: bool = False,
    ) -> None:
        self._target = target_duration_seconds
        self._raises_at = raises_at_seconds
        self._use_real_sleep = use_real_sleep

    async def ainvoke(self, state: WorkflowState) -> WorkflowState:
        """Simulate a workflow run.

        If raises_at_seconds is set and target_duration_seconds >= raises_at_seconds,
        raises SoftTimeLimitExceeded to simulate the Celery soft limit firing.

        Returns:
            Updated WorkflowState with status=COMPLETED.
        """
        # Build a fake SLTE that the guard can recognize by class name
        class SoftTimeLimitExceeded(Exception):
            pass

        if self._raises_at is not None and self._target >= self._raises_at:
            if self._use_real_sleep:
                await asyncio.sleep(0.001)
            raise SoftTimeLimitExceeded(
                f"Soft time limit exceeded at {self._raises_at}s"
            )

        if self._use_real_sleep:
            await asyncio.sleep(self._target)

        return state.model_copy(update={"status": WorkflowStatus.COMPLETED})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_workflow_state():
    """Fixture returning the build_fake_workflow_state factory."""
    return build_fake_workflow_state


@pytest.fixture()
def fake_clock():
    """Return a FakeWorkflowClock with 0 elapsed seconds by default."""
    return FakeWorkflowClock(elapsed_seconds=0.0)
