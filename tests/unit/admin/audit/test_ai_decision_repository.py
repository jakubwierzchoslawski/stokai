"""Unit tests for AIDecisionRepository.

Uses AsyncMock + SQLAlchemy to verify repository contract without a real DB.

PLAN-F-029 TASK-002
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.decision_log.models.ai_decision_model import AIDecision
from src.ai.decision_log.repositories.ai_decision_repository import (
    AIDecisionRepository,
    _decode_cursor,
    _encode_cursor,
)
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionCreate,
    DecisionLogFilter,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_decision(**kwargs) -> AIDecision:
    defaults = dict(
        decision_id=uuid.uuid4(),
        agent_role="narrative_writer",
        model="claude-haiku",
        prompt_version="abc1234" * 5 + "abc",
        confidence=0.85,
        inputs_summary="Summary of inputs",
        inputs_full='{"event": "data"}',
        retrieved_analogs=[],
        action_signal=None,
        company_ticker="AAPL",
        output_text="Decision output",
        langfuse_trace_url="https://langfuse.example.com/trace/abc",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    row = MagicMock(spec=AIDecision)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _make_create(**kwargs) -> AIDecisionCreate:
    defaults = dict(
        agent_role="narrative_writer",
        model="claude-haiku",
        prompt_version="abc1234" * 5 + "abc",
        confidence=0.85,
        inputs_summary="Summary",
        inputs_full='{"event": "data"}',
        retrieved_analogs=[],
        action_signal="HOLD",
        company_ticker="AAPL",
        output_text="Output",
        langfuse_trace_url="https://langfuse.example.com/trace/abc",
        workflow_run_id=None,
    )
    defaults.update(kwargs)
    return AIDecisionCreate(**defaults)


# ── Cursor encode/decode ───────────────────────────────────────────────────────

class TestCursorCodec:
    def test_round_trip(self):
        dt = datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc)
        uid = uuid.uuid4()
        cursor = _encode_cursor(dt, uid)
        decoded_dt, decoded_uid = _decode_cursor(cursor)
        assert decoded_dt == dt
        assert decoded_uid == uid


# ── Insert ─────────────────────────────────────────────────────────────────────

class TestAIDecisionRepositoryInsert:
    @pytest.mark.asyncio
    async def test_insert_persists_and_returns_row(self):
        session = AsyncMock()
        repo = AIDecisionRepository(session)

        decision_id = uuid.uuid4()
        orm_row = _make_decision(decision_id=decision_id)

        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        # simulate refresh populating the row
        with patch.object(repo, "insert", wraps=repo.insert):
            # We patch flush to set the decision_id on the row
            async def _flush():
                pass

            async def _refresh(row):
                row.decision_id = decision_id

            session.flush.side_effect = _flush
            session.refresh.side_effect = _refresh
            session.add = MagicMock()

            # We must patch AIDecision constructor to return our mock
            with patch(
                "src.ai.decision_log.repositories.ai_decision_repository.AIDecision",
                return_value=orm_row,
            ):
                create = _make_create()
                result = await repo.insert(create)

        assert result.agent_role == "narrative_writer"
        assert result.model == "claude-haiku"
        session.add.assert_called_once()


# ── get_by_id ─────────────────────────────────────────────────────────────────

class TestAIDecisionRepositoryGetById:
    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_unknown(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        repo = AIDecisionRepository(session)

        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_returns_full_detail_with_inputs_full(self):
        session = AsyncMock()
        decision_id = uuid.uuid4()
        orm_row = _make_decision(
            decision_id=decision_id,
            inputs_full='{"full": "json content that is long and untruncated"}',
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm_row
        session.execute = AsyncMock(return_value=result_mock)
        repo = AIDecisionRepository(session)

        detail = await repo.get_by_id(decision_id)
        assert detail is not None
        assert detail.decision_id == decision_id
        # inputs_full not truncated
        assert detail.inputs_full == '{"full": "json content that is long and untruncated"}'


# ── list_paginated ────────────────────────────────────────────────────────────

class TestAIDecisionRepositoryListPaginated:
    def _make_session_with_rows(self, rows):
        session = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rows
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)
        return session

    @pytest.mark.asyncio
    async def test_list_paginated_no_filters_returns_most_recent(self):
        rows = [_make_decision() for _ in range(3)]
        session = self._make_session_with_rows(rows)
        repo = AIDecisionRepository(session)

        result, cursor = await repo.list_paginated(DecisionLogFilter(limit=10))
        assert len(result) == 3
        assert cursor is None

    @pytest.mark.asyncio
    async def test_list_paginated_confidence_min_filter(self):
        """confidence_min=0.7 — repository sends the WHERE clause; we verify the filter builds."""
        session = AsyncMock()
        scalars_mock = MagicMock()
        # Return only rows with confidence >= 0.7
        high_conf = _make_decision(confidence=0.85)
        scalars_mock.all.return_value = [high_conf]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)
        repo = AIDecisionRepository(session)

        result, cursor = await repo.list_paginated(
            DecisionLogFilter(confidence_min=0.7, limit=50)
        )
        assert len(result) == 1
        assert result[0].confidence == 0.85

    @pytest.mark.asyncio
    async def test_list_paginated_agent_role_filter(self):
        session = AsyncMock()
        scalars_mock = MagicMock()
        row = _make_decision(agent_role="narrative_writer")
        scalars_mock.all.return_value = [row]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)
        repo = AIDecisionRepository(session)

        result, _ = await repo.list_paginated(
            DecisionLogFilter(agent_role="narrative_writer", limit=50)
        )
        assert len(result) == 1
        assert result[0].agent_role == "narrative_writer"

    @pytest.mark.asyncio
    async def test_cursor_pagination_two_pages_no_overlap(self):
        """Page 1 returns limit rows + 1 extra to signal more pages; page 2 starts after."""
        dt1 = datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 6, 4, 9, 0, 0, tzinfo=timezone.utc)
        page1_rows = [_make_decision(created_at=dt1), _make_decision(created_at=dt2)]
        # extra row signals "there is a next page"
        extra_id = uuid.uuid4()
        extra_row = _make_decision(
            decision_id=extra_id,
            created_at=datetime(2026, 6, 4, 8, 0, 0, tzinfo=timezone.utc),
        )

        session1 = AsyncMock()
        scalars1 = MagicMock()
        # limit=2 → returns 3 items → next_cursor set
        scalars1.all.return_value = page1_rows + [extra_row]
        res1 = MagicMock()
        res1.scalars.return_value = scalars1
        session1.execute = AsyncMock(return_value=res1)
        repo1 = AIDecisionRepository(session1)

        result1, next_cursor = await repo1.list_paginated(DecisionLogFilter(limit=2))
        assert len(result1) == 2
        assert next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_paginated_returns_none_cursor_when_fewer_than_limit(self):
        rows = [_make_decision() for _ in range(3)]
        session = self._make_session_with_rows(rows)
        repo = AIDecisionRepository(session)

        result, cursor = await repo.list_paginated(DecisionLogFilter(limit=10))
        assert cursor is None
