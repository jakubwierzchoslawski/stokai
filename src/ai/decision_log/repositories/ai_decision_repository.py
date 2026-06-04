"""AIDecisionRepository — SQLAlchemy 2.0 async implementation.

PLAN-F-029 TASK-002
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.decision_log.interfaces.i_ai_decision_repository import (
    IAIDecisionRepository,
)
from src.ai.decision_log.models.ai_decision_model import AIDecision
from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionCreate,
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)

_CURSOR_SEP = "|"


def _encode_cursor(created_at: datetime, decision_id: UUID) -> str:
    payload = f"{created_at.isoformat()}{_CURSOR_SEP}{decision_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, uuid_str = decoded.split(_CURSOR_SEP, 1)
    return datetime.fromisoformat(ts_str), UUID(uuid_str)


class AIDecisionRepository(IAIDecisionRepository):
    """SQLAlchemy 2.0 async repository for the ai_decision table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, decision: AIDecisionCreate) -> AIDecisionRow:
        row = AIDecision(
            agent_role=decision.agent_role,
            model=decision.model,
            prompt_version=decision.prompt_version,
            confidence=decision.confidence,
            inputs_summary=decision.inputs_summary,
            inputs_full=decision.inputs_full,
            retrieved_analogs=decision.retrieved_analogs,
            action_signal=decision.action_signal,
            company_ticker=decision.company_ticker,
            output_text=decision.output_text,
            langfuse_trace_url=decision.langfuse_trace_url,
            workflow_run_id=decision.workflow_run_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return AIDecisionRow.from_orm_model(row)

    async def get_by_id(self, decision_id: UUID) -> Optional[AIDecisionDetail]:
        stmt = sa.select(AIDecision).where(AIDecision.decision_id == decision_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return AIDecisionDetail(
            decision_id=row.decision_id,
            agent_role=row.agent_role,
            model=row.model,
            prompt_version=row.prompt_version,
            confidence=row.confidence,
            inputs_summary=row.inputs_summary,
            inputs_full=row.inputs_full,
            retrieved_analogs=row.retrieved_analogs or [],
            action_signal=row.action_signal,
            company_ticker=row.company_ticker,
            output_text=row.output_text,
            langfuse_trace_url=row.langfuse_trace_url,
            workflow_run_id=row.workflow_run_id,
            created_at=row.created_at,
        )

    async def list_paginated(
        self, filters: DecisionLogFilter
    ) -> Tuple[list[AIDecisionRow], Optional[str]]:
        conditions: list[sa.ColumnElement] = []

        if filters.date_from is not None:
            conditions.append(AIDecision.created_at >= filters.date_from)
        if filters.date_to is not None:
            conditions.append(AIDecision.created_at <= filters.date_to)
        if filters.agent_role is not None:
            conditions.append(AIDecision.agent_role == filters.agent_role)
        if filters.model is not None:
            conditions.append(AIDecision.model == filters.model)
        if filters.confidence_min is not None:
            conditions.append(AIDecision.confidence >= filters.confidence_min)
        if filters.confidence_max is not None:
            conditions.append(AIDecision.confidence <= filters.confidence_max)
        if filters.action_signal is not None:
            conditions.append(AIDecision.action_signal == filters.action_signal)
        if filters.company_ticker is not None:
            conditions.append(AIDecision.company_ticker == filters.company_ticker)

        # Keyset pagination
        if filters.cursor is not None:
            try:
                cursor_ts, cursor_id = _decode_cursor(filters.cursor)
                conditions.append(
                    sa.or_(
                        AIDecision.created_at < cursor_ts,
                        sa.and_(
                            AIDecision.created_at == cursor_ts,
                            AIDecision.decision_id < cursor_id,
                        ),
                    )
                )
            except Exception:
                # Invalid cursor treated as no cursor
                pass

        stmt = (
            sa.select(AIDecision)
            .where(*conditions)
            .order_by(AIDecision.created_at.desc(), AIDecision.decision_id.desc())
            .limit(filters.limit + 1)
        )

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        next_cursor: Optional[str] = None
        if len(rows) > filters.limit:
            rows = list(rows[: filters.limit])
            last = rows[-1]
            next_cursor = _encode_cursor(last.created_at, last.decision_id)
        else:
            rows = list(rows)

        return [AIDecisionRow.from_orm_model(r) for r in rows], next_cursor
