"""
SeedingCheckpointRepository — persistence layer for cold-start seeding state.

Tracks per-batch progress so the seeding pipeline can resume after container
restarts or failures (12-factor, REQ-N-007).

Schema (seeding_checkpoint table):
    batch_key   TEXT PRIMARY KEY  — e.g. 'gdelt:1979-01-01:1979-01-31'
    state       TEXT NOT NULL     — pending | in_progress | done | failed
    events_seeded   INT DEFAULT 0
    embeddings_done INT DEFAULT 0
    error_detail    TEXT
    started_at      TIMESTAMPTZ
    completed_at    TIMESTAMPTZ
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.cold_start.types import CheckpointState

logger = logging.getLogger(__name__)


@dataclass
class CheckpointRow:
    """Represents a single row in the seeding_checkpoint table."""

    batch_key: str
    state: CheckpointState
    events_seeded: int
    embeddings_done: int
    error_detail: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class ISeedingCheckpointRepository(ABC):
    """Abstract contract for checkpoint persistence."""

    @abstractmethod
    async def get_checkpoint(self, batch_key: str) -> CheckpointRow | None:
        """Return the checkpoint row for batch_key, or None if not found."""
        ...

    @abstractmethod
    async def upsert_checkpoint(
        self,
        batch_key: str,
        state: CheckpointState,
        meta: dict[str, Any],
    ) -> None:
        """Insert or update the checkpoint row for batch_key.

        meta may contain any of: events_seeded, embeddings_done, error_detail,
        started_at, completed_at.
        """
        ...

    @abstractmethod
    async def list_pending_batches(
        self,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """Return batch_keys whose state is not 'done', within the date range.

        batch_key format: '<provider>:<YYYY-MM-DD>:<YYYY-MM-DD>'
        The start_date/end_date parameters filter by the date embedded in the key.
        """
        ...


class SeedingCheckpointRepository(ISeedingCheckpointRepository):
    """SQLAlchemy 2.0 async implementation of ISeedingCheckpointRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the SQLAlchemy async session (DIP)."""
        self._session = session

    async def get_checkpoint(self, batch_key: str) -> CheckpointRow | None:
        """Return the checkpoint row for batch_key, or None if not found."""
        result = await self._session.execute(
            text(
                """
                SELECT batch_key, state, events_seeded, embeddings_done,
                       error_detail, started_at, completed_at, updated_at
                FROM seeding_checkpoint
                WHERE batch_key = :batch_key
                """
            ),
            {"batch_key": batch_key},
        )
        row = result.fetchone()
        if row is None:
            return None
        return self._row_to_checkpoint(row)

    async def upsert_checkpoint(
        self,
        batch_key: str,
        state: CheckpointState,
        meta: dict[str, Any],
    ) -> None:
        """Insert or update a checkpoint row (ON CONFLICT DO UPDATE)."""
        now = datetime.now(tz=timezone.utc)
        events_seeded = meta.get("events_seeded", 0)
        embeddings_done = meta.get("embeddings_done", 0)
        error_detail = meta.get("error_detail", None)
        started_at = meta.get("started_at", None)
        completed_at = meta.get("completed_at", None)

        await self._session.execute(
            text(
                """
                INSERT INTO seeding_checkpoint
                    (batch_key, state, events_seeded, embeddings_done,
                     error_detail, started_at, completed_at, updated_at)
                VALUES
                    (:batch_key, :state, :events_seeded, :embeddings_done,
                     :error_detail, :started_at, :completed_at, :updated_at)
                ON CONFLICT (batch_key) DO UPDATE SET
                    state         = EXCLUDED.state,
                    events_seeded = EXCLUDED.events_seeded,
                    embeddings_done = EXCLUDED.embeddings_done,
                    error_detail  = EXCLUDED.error_detail,
                    started_at    = COALESCE(seeding_checkpoint.started_at, EXCLUDED.started_at),
                    completed_at  = EXCLUDED.completed_at,
                    updated_at    = EXCLUDED.updated_at
                """
            ),
            {
                "batch_key": batch_key,
                "state": state.value,
                "events_seeded": events_seeded,
                "embeddings_done": embeddings_done,
                "error_detail": error_detail,
                "started_at": started_at,
                "completed_at": completed_at,
                "updated_at": now,
            },
        )
        await self._session.commit()
        logger.debug("Upserted checkpoint: key=%s state=%s", batch_key, state.value)

    async def list_pending_batches(
        self,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """Return batch_keys whose state is not 'done', within the date range.

        Filters by the start date embedded in the batch_key (second component
        when split on ':').
        """
        result = await self._session.execute(
            text(
                """
                SELECT batch_key
                FROM seeding_checkpoint
                WHERE state != 'done'
                ORDER BY batch_key
                """
            )
        )
        rows = result.fetchall()

        # Filter by the date range encoded in the key: '<provider>:YYYY-MM-DD:YYYY-MM-DD'
        pending = []
        for (batch_key,) in rows:
            try:
                parts = batch_key.split(":")
                if len(parts) >= 3:
                    key_start = date.fromisoformat(parts[1])
                    if start_date <= key_start <= end_date:
                        pending.append(batch_key)
                else:
                    # Key without date encoding — include it
                    pending.append(batch_key)
            except (ValueError, IndexError):
                # Malformed key — include conservatively
                pending.append(batch_key)

        return pending

    @staticmethod
    def _row_to_checkpoint(row: Any) -> CheckpointRow:
        """Map a raw DB row to a CheckpointRow dataclass."""
        return CheckpointRow(
            batch_key=row[0],
            state=CheckpointState(row[1]),
            events_seeded=row[2],
            embeddings_done=row[3],
            error_detail=row[4],
            started_at=row[5],
            completed_at=row[6],
            updated_at=row[7],
        )
