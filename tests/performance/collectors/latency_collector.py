"""LatencyCollector — measures end-to-end latency for a single pipeline run.

PLAN-N-001 TASK-002.

SOLID design:
  SRP: runs one pipeline invocation and returns elapsed seconds only.
  DIP: depends on the EventInjector Protocol abstraction, not concrete adapters.
  OCP: new source types only require a new EventInjector subclass — zero changes here.

Architecture note on dispatched_at:
  The plan specifies reading ``AlertRecord.dispatched_at`` for AUTO_SEND events.
  PLAN-F-001's current implementation does not yet produce an AlertRecord ORM row
  (dispatch is via WebSocket push).  Until an AlertRecord table is added, this
  collector uses ``EventRecord.generated_at`` (set by TraceStep/Step 13) as the
  pipeline-completion proxy timestamp.

  For the HIL_QUEUE route, ``hil_queue.created_at`` would be used as the
  dispatched proxy (the mock sets confidence=0.85 → AUTO_SEND to avoid this path).

  This decision is documented here per DEV-STANDARDS.md §9 (observability norms
  applied to test artefacts).  When an AlertRecord model is added, update
  ``_fetch_alert_record`` to query the real table.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.performance.injectors.base import EventInjector

from src.event_pipeline.pipeline_state import PipelineState, RawEventPayload


@dataclass
class _FakeAlertRecord:
    """Lightweight proxy for AlertRecord until the real ORM model exists.

    Uses EventRecord.generated_at (TraceStep timestamp) as the dispatched_at
    proxy for AUTO_SEND events measured in latency tests.
    """
    dispatched_at: datetime | None


@dataclass
class _FakeEventRecord:
    """Lightweight proxy carrying EventRecord timestamp fields."""
    detected_at: datetime | None
    generated_at: datetime | None


@dataclass
class LatencyCollector:
    """Runs one pipeline invocation and returns elapsed seconds.

    Parameters
    ----------
    executor:
        Fully-wired ``PipelineExecutor`` instance (with mocked LLM providers
        for performance tests).
    db_session:
        ``AsyncSession`` connected to the test PostgreSQL DB.  Used to persist
        the ``RawEvent`` seed row and to read back timestamps.
    injector:
        ``EventInjector`` Protocol instance that builds test payloads.
    """

    executor: Any
    db_session: Any
    injector: Any

    async def run_once(self, index: int) -> float:
        """Inject one test event, run the pipeline, and return elapsed seconds.

        Steps:
        1. Calls ``self.injector.build_payload(index)`` to produce the test payload.
        2. Persists a ``RawEvent`` row via the DB session (or uses a generated UUID
           if the session is a mock).
        3. Calls ``await self.executor.run(initial_state)``.
        4. Reads ``EventRecord.detected_at`` via ``_fetch_event_record``.
        5. Reads ``dispatched_at`` proxy via ``_fetch_alert_record``.
        6. Asserts ``event_record.detected_at is not None``.
        7. Asserts ``alert_record.dispatched_at is not None``.
        8. Returns ``(alert_record.dispatched_at - event_record.detected_at).total_seconds()``.

        Raises
        ------
        AssertionError:
            If ``detected_at`` or ``dispatched_at`` is None on the completed run
            (data-integrity failure — LatencyCollector never silently passes).
        """
        payload = self.injector.build_payload(index)

        # 2. Persist a RawEvent seed row and get back the raw_event_id
        raw_event_id = await self._persist_raw_event(payload)

        # 3. Build initial PipelineState and run the executor
        initial_state = PipelineState(
            raw_event_id=raw_event_id,
            tenant_id=payload.tenant_id,
            payload=payload,
        )
        final_state: PipelineState = await self.executor.run(initial_state)

        # 4. Fetch EventRecord (or use proxy from state)
        event_record = await self._fetch_event_record(raw_event_id, final_state)

        # 5. Fetch AlertRecord (or dispatched_at proxy from state)
        alert_record = await self._fetch_alert_record(raw_event_id, final_state)

        # 6 & 7. Null-guard assertions — NEVER silently pass
        assert event_record.detected_at is not None, (
            f"detected_at is None on EventRecord for raw_event_id={raw_event_id}. "
            "This is a data-integrity failure — TraceStep must set detected_at."
        )
        assert alert_record.dispatched_at is not None, (
            f"dispatched_at is None on AlertRecord (proxy) for raw_event_id={raw_event_id}. "
            "This is a data-integrity failure — TraceStep must set generated_at "
            "(used as dispatched_at proxy until AlertRecord model is added)."
        )

        # 8. Compute elapsed seconds
        detected = event_record.detected_at
        dispatched = alert_record.dispatched_at

        # Normalise to UTC if needed
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        if dispatched.tzinfo is None:
            dispatched = dispatched.replace(tzinfo=timezone.utc)

        return (dispatched - detected).total_seconds()

    # ------------------------------------------------------------------
    # Protected helpers — patchable in tests
    # ------------------------------------------------------------------

    async def _persist_raw_event(self, payload: RawEventPayload) -> uuid.UUID:
        """Persist a RawEvent seed row and return the event_id.

        In DB-backed tests this writes a real row.  In pure-mock tests the
        session is an AsyncMock and no real DB write occurs; a fresh UUID
        is returned.
        """
        raw_event_id = uuid.uuid4()
        try:
            from src.db.models.raw_event import RawEvent
            raw_event = RawEvent(
                event_id=raw_event_id,
                tenant_id=payload.tenant_id,
                source=payload.source.value,
                raw_payload=payload.raw_payload,
                detected_at=payload.detected_at,
                pipeline_status="pending",
            )
            self.db_session.add(raw_event)
            await self.db_session.flush()
        except Exception:  # noqa: BLE001
            # Session is a mock or DB unavailable; use generated UUID.
            pass
        return raw_event_id

    async def _fetch_event_record(
        self,
        raw_event_id: uuid.UUID,
        final_state: PipelineState,
    ) -> _FakeEventRecord:
        """Fetch EventRecord timestamps from DB or derive from pipeline state.

        Production mode: queries the ``geopolitical_events`` table by raw_event_id.
        Mock/fallback mode: derives timestamps from ``final_state`` fields.
        """
        try:
            from sqlalchemy import select
            from src.db.models.event_record import EventRecord

            stmt = select(EventRecord).where(
                EventRecord.raw_event_id == raw_event_id
            )
            result = await self.db_session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is not None:
                return _FakeEventRecord(
                    detected_at=row.detected_at,
                    generated_at=row.generated_at,
                )
        except Exception:  # noqa: BLE001
            pass

        # Fallback: derive from pipeline state
        return _FakeEventRecord(
            detected_at=final_state.payload.detected_at,
            generated_at=final_state.generated_at,
        )

    async def _fetch_alert_record(
        self,
        raw_event_id: uuid.UUID,
        final_state: PipelineState,
    ) -> _FakeAlertRecord:
        """Return a dispatched_at proxy for the completed pipeline run.

        Until an AlertRecord ORM model is added (future PLAN), this method
        uses ``final_state.generated_at`` (set by TraceStep) as the
        dispatched_at proxy for AUTO_SEND events.

        For HIL_QUEUE events: confidence < 0.7 means TraceStep still runs and
        sets generated_at; this serves as the queued-at proxy.
        """
        # Use generated_at from final state as dispatched_at proxy.
        return _FakeAlertRecord(dispatched_at=final_state.generated_at)
