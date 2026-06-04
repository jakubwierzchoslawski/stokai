"""
storage.repositories.workflow_run_repository — WorkflowRunRepository.

Provides create / get / update_status / save_final_state / save_timeout operations
over the workflow_run table.  Every query is scoped by tenant_id to prevent IDOR
leakage.

PLAN-F-010 will later extend this repository with additional query methods.
PLAN-N-002 adds save_timeout().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.workflows.errors import WorkflowRunNotFoundError
from src.ai.workflows.state import WorkflowState, WorkflowStatus
from src.storage.models.workflow_run import WorkflowRun


class WorkflowRunRepository:
    """SQLAlchemy 2.0 async repository for the workflow_run table.

    Constructor-injected AsyncSession — no session creation inside methods (DIP).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IWorkflowRunRepository contract ──────────────────────────────────────

    async def create(self, state: WorkflowState) -> WorkflowRun:
        """INSERT a new workflow_run row from a WorkflowState and return the ORM row."""
        orm = WorkflowRun(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type.value,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            company_id=state.company_id,
            status=state.status.value,
            started_at=state.started_at,
            cost_usd=state.cost_usd,
            langfuse_trace_id=state.langfuse_trace_id,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def get(self, workflow_id: UUID, tenant_id: UUID) -> WorkflowRun | None:
        """Return the WorkflowRun scoped to tenant_id, or None.

        The tenant_id guard prevents IDOR: a user from a different tenant
        querying a valid workflow_id will receive None, not a 403.
        """
        stmt = select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        workflow_id: UUID,
        status: WorkflowStatus,
        **kwargs,
    ) -> None:
        """Update status and any additional columns supplied as keyword arguments.

        Allowed keyword overrides: completed_at, cost_usd, langfuse_trace_id.
        Unknown keys are silently ignored to prevent accidental column injection.
        """
        allowed_columns = {"completed_at", "cost_usd", "langfuse_trace_id"}
        values: dict = {"status": status.value}
        for key, val in kwargs.items():
            if key in allowed_columns:
                values[key] = val

        stmt = (
            update(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def create_workflow_run(self, state: WorkflowState) -> WorkflowRun:
        """Alias for create() — used by CostAwareBaseWorkflow dispatch layer."""
        return await self.create(state)

    async def update_workflow_run(
        self,
        workflow_id: UUID,
        *,
        status: str,
        cost_usd: float | None = None,
        cost_limited: bool | None = None,
        completed_at: datetime | None = None,
        final_state_json: dict | None = None,
    ) -> None:
        """Update workflow_run columns by workflow_id.

        Used by CostAwareBaseWorkflow for status transitions that include
        cost_limited (PLAN-N-004).

        Allowed columns: status, cost_usd, cost_limited, completed_at, final_state.
        """
        values: dict = {"status": status}
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if cost_limited is not None:
            values["cost_limited"] = cost_limited
        if completed_at is not None:
            values["completed_at"] = completed_at
        if final_state_json is not None:
            values["final_state"] = final_state_json

        stmt = (
            update(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def save_final_state(
        self, workflow_id: UUID, final_state: WorkflowState
    ) -> None:
        """Persist the completed WorkflowState as JSONB in final_state column.

        Also updates status, cost_usd, and completed_at from final_state.
        """
        stmt = (
            update(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .values(
                status=final_state.status.value,
                cost_usd=final_state.cost_usd,
                completed_at=datetime.now(tz=timezone.utc),
                final_state=json.loads(final_state.model_dump_json()),
                langfuse_trace_id=final_state.langfuse_trace_id,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def save_timeout(
        self,
        workflow_id: UUID,
        partial_state: WorkflowState,
        timeout_at: datetime,
    ) -> None:
        """Persist partial state with status=TIMEOUT when SoftTimeLimitExceeded fires.

        Uses an UPDATE ... WHERE workflow_id = ? AND tenant_id = ? approach so a
        missing row does not silently swallow the failure — rowcount is checked and
        WorkflowRunNotFoundError is raised if zero rows were updated.

        Sets: status='TIMEOUT', partial_result=True, timeout_at=timeout_at,
              final_state=partial_state.model_dump(), completed_at=timeout_at.

        Enforces tenant_id scoping from partial_state.tenant_id (§12.3).

        Args:
            workflow_id:    UUID of the workflow run to update.
            partial_state:  Partially-completed WorkflowState at timeout.
            timeout_at:     UTC timestamp when SoftTimeLimitExceeded fired.

        Raises:
            WorkflowRunNotFoundError: If no row matches (workflow_id, tenant_id).
        """
        stmt = (
            update(WorkflowRun)
            .where(
                WorkflowRun.workflow_id == workflow_id,
                WorkflowRun.tenant_id == partial_state.tenant_id,
            )
            .values(
                status=WorkflowStatus.TIMEOUT.value,
                partial_result=True,
                timeout_at=timeout_at,
                completed_at=timeout_at,
                final_state=json.loads(partial_state.model_dump_json()),
                cost_usd=partial_state.cost_usd,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()

        if result.rowcount == 0:
            raise WorkflowRunNotFoundError(workflow_id)

    # ── Additional query helpers ──────────────────────────────────────────────

    async def get_active_for_company_user(
        self, company_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> WorkflowRun | None:
        """Return the active (RUNNING or HIL_PENDING) run for a company+user pair.

        Used by the rate-limit check in the trigger endpoint: one active analysis
        per company per user at a time.
        """
        stmt = select(WorkflowRun).where(
            WorkflowRun.company_id == company_id,
            WorkflowRun.user_id == user_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.status.in_(["RUNNING", "HIL_PENDING"]),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
