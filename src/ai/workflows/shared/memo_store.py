"""
ai.workflows.shared.memo_store — MemoStore: atomic Brief + WorkflowRun persistence.

MemoStore.persist() writes a Brief row and updates the WorkflowRun status in a
single logical operation.  Each caller is responsible for providing an open
session/unit-of-work so callers can wrap this in a transaction if needed.

PLAN-F-010 TASK-009.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.event_deep_dive.state import BriefCreate, DeepDiveWorkflowState
from src.ai.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)


class MemoStore:
    """Persists a DeepDive memo (Brief) + updates the WorkflowRun status.

    No session is held internally — callers inject the repository objects
    so that transaction management stays with the caller (DIP / testability).

    Usage::

        store = MemoStore()
        brief = await store.persist(
            state=state,
            workflow_run_repo=workflow_run_repo,
            brief_repo=brief_repo,
            confidence=0.82,
            cost_limited=False,
        )
    """

    async def persist(
        self,
        state: DeepDiveWorkflowState,
        workflow_run_repo: Any,
        brief_repo: Any,
        confidence: float,
        cost_limited: bool,
    ) -> Any:
        """Atomically insert a Brief and update WorkflowRun status.

        Builds a BriefCreate from state.memo_draft and calls
        brief_repo.insert_memo(), then calls workflow_run_repo.update_status()
        to mark the run as COMPLETED (or COST_LIMIT).

        Args:
            state: Completed DeepDiveWorkflowState (memo_draft must be set).
            workflow_run_repo: IWorkflowRunRepository implementation.
            brief_repo: IBriefRepository implementation.
            confidence: Final workflow confidence value.
            cost_limited: Whether the run hit a cost ceiling.

        Returns:
            The inserted Brief ORM object (with populated brief_id).

        Raises:
            ValueError: If state.event_full is None (event_id cannot be resolved).
        """
        if state.event_full is None:
            raise ValueError(
                "state.event_full must be set before MemoStore.persist() is called"
            )

        # Build content dict from memo_draft (or empty if not set)
        content: dict = {}
        if state.memo_draft is not None:
            content = state.memo_draft.model_dump(mode="json")

        brief_create = BriefCreate(
            event_id=state.event_full.event_id,
            tenant_id=state.tenant_id,
            content=content,
            confidence=confidence,
            cost_usd=state.cost_usd,
            cost_limited=cost_limited,
        )

        # 1. Insert brief
        brief = await brief_repo.insert_memo(brief_create)
        logger.info(
            "MemoStore.persist: inserted brief_id=%s event_id=%s confidence=%.3f cost_limited=%s",
            brief.brief_id,
            state.event_full.event_id,
            confidence,
            cost_limited,
        )

        # 2. Update WorkflowRun status
        final_status = (
            WorkflowStatus.COST_LIMIT if cost_limited else WorkflowStatus.COMPLETED
        )
        await workflow_run_repo.update_status(
            state.workflow_id,
            final_status,
            cost_usd=state.cost_usd,
        )
        logger.info(
            "MemoStore.persist: workflow_run %s → status=%s",
            state.workflow_id,
            final_status.value,
        )

        return brief
