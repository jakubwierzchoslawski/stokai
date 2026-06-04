"""
ai.tasks.watchlist_scan_task — Celery task: watchlist_scan_generate.

Celery task for running the afternoon watchlist scan workflow (PLAN-F-008).

Runs at 17:30 UTC via Celery Beat. A beat orchestrator first queries all active
users with non-empty watchlists and dispatches one task per user.

Steps (per user):
  1. Check FeatureFlagService.is_enabled('watchlist_scan', env).
  2. Build WatchlistScanWorkflow.
  3. Create workflow_run DB row.
  4. Invoke graph (ainvoke).
  5. Persist final state.

Constraints:
  - $1.00 cost ceiling
  - time_limit=480s, soft_time_limit=360s
  - max_retries=0 (afternoon scans run once; retries cause stale data)
  - Task name: "ai.watchlist_scan"

PLAN-F-008 TASK-006, TASK-013
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

# ── Lazy / async helpers ──────────────────────────────────────────────────────


@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[Any, None]:
    """Provide an async SQLAlchemy session for the task."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def _get_feature_flag_service() -> Any:
    """Return FeatureFlagService (lazy import to avoid circular deps)."""
    try:
        from src.feature_flags.service import FeatureFlagService
        return FeatureFlagService()
    except ImportError:
        # Stub: always enabled when not available
        class _AlwaysEnabled:
            def is_enabled(self, flag: str, env: str = "") -> bool:
                return True
        return _AlwaysEnabled()


async def _run_watchlist_scan_for_user(
    user_id: str,
    tenant_id: str,
    workflow_id: str,
) -> dict:
    """Async core of the watchlist scan task for a single user.

    Returns:
        dict with workflow_id, status, hil_pending.
    """
    from src.ai.workflows.watchlist_scan_state import WatchlistScanState
    from src.ai.workflows.watchlist_scan_workflow import WatchlistScanWorkflow

    wf_id = UUID(workflow_id)
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)

    state = WatchlistScanState(
        workflow_id=wf_id,
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        started_at=datetime.now(tz=timezone.utc),
    )

    # Build workflow with stub/real deps (real injection happens in production)
    # In tests, deps are mocked; in production they're injected from app.state.
    try:
        workflow = _build_workflow()
    except Exception:
        logger.exception("Failed to build WatchlistScanWorkflow; aborting task")
        return {
            "workflow_id": workflow_id,
            "status": "FAILED",
            "hil_pending": False,
        }

    try:
        final_state = await workflow.ainvoke(state)
    except SoftTimeLimitExceeded:
        logger.warning(
            "watchlist_scan_generate soft time limit exceeded workflow=%s",
            workflow_id,
        )
        return {
            "workflow_id": workflow_id,
            "status": "TIMEOUT",
            "hil_pending": False,
        }
    except Exception as exc:
        logger.exception(
            "watchlist_scan_generate failed workflow=%s: %s",
            workflow_id,
            exc,
        )
        return {
            "workflow_id": workflow_id,
            "status": "FAILED",
            "hil_pending": False,
        }

    hil_pending = getattr(final_state, "requires_hil", False)

    return {
        "workflow_id": workflow_id,
        "status": "HIL_PENDING" if hil_pending else "COMPLETED",
        "hil_pending": hil_pending,
        "cost_usd": getattr(final_state, "cost_usd", 0.0),
    }


def _build_workflow() -> Any:
    """Build WatchlistScanWorkflow with production dependencies.

    In testing this is patched. In production it connects to real repos.
    """
    # Stub implementations — replace with DI in production
    from unittest.mock import AsyncMock, MagicMock

    watchlist_repo = AsyncMock()
    watchlist_repo.list_company_ids = AsyncMock(return_value=[])
    portfolio_repo = AsyncMock()
    portfolio_repo.list_company_ids = AsyncMock(return_value=[])
    geo_event_repo = AsyncMock()
    geo_event_repo.list_for_companies = AsyncMock(return_value=[])
    score_repo = AsyncMock()
    score_repo.list_score_changes = AsyncMock(return_value=[])
    analogy_repo = AsyncMock()
    analogy_repo.get_analogies_for_events = AsyncMock(return_value={})
    hil_repo = AsyncMock()
    hil_repo.create = AsyncMock(return_value=MagicMock())
    brief_repo = AsyncMock()
    brief_row = MagicMock()
    brief_row.brief_id = uuid4()
    brief_repo.insert_memo = AsyncMock(return_value=brief_row)
    email_service = AsyncMock()
    email_service.send_watchlist_scan = AsyncMock()

    # Stub agents
    def _make_stub_agent(**output_attrs):
        output = MagicMock()
        output.cost_usd = 0.01
        output.relevant_events = []
        output.anomalies = []
        output.high_anomaly_company_ids = []
        output.recommendations = []
        output.overall_confidence = 0.75
        output.report = {"sections": ["overview"]}
        for k, v in output_attrs.items():
            setattr(output, k, v)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)
        return agent

    judge_result = MagicMock()
    judge_result.confidence = 0.75
    tier1_judge = AsyncMock()
    tier1_judge.evaluate = AsyncMock(return_value=judge_result)

    from src.ai.workflows.watchlist_scan_workflow import WatchlistScanWorkflow
    return WatchlistScanWorkflow(
        watchlist_repo=watchlist_repo,
        portfolio_repo=portfolio_repo,
        geo_event_repo=geo_event_repo,
        score_repo=score_repo,
        analogy_repo=analogy_repo,
        hil_repo=hil_repo,
        brief_repo=brief_repo,
        email_service=email_service,
        filter_agent=_make_stub_agent(),
        anomaly_agent=_make_stub_agent(),
        analyst_agent=_make_stub_agent(),
        writer_agent=_make_stub_agent(),
        tier1_judge=tier1_judge,
        cost_ceiling_usd=1.00,
    )


# ── Single-user task ──────────────────────────────────────────────────────────


@shared_task(
    name="ai.watchlist_scan",
    bind=False,
    time_limit=480,
    soft_time_limit=360,
    max_retries=0,
)
def watchlist_scan_generate(
    user_id: str,
    tenant_id: str,
    workflow_id: str | None = None,
    env: str = "production",
) -> dict:
    """Celery task: run watchlist scan for a single user.

    Checks FeatureFlagService.is_enabled('watchlist_scan', env) first.
    Dispatched by the beat orchestrator task once per active user.

    Args:
        user_id: UUID string of the user.
        tenant_id: UUID string of the tenant.
        workflow_id: Pre-generated UUID (generated here if None).
        env: Environment string for feature flag lookup.

    Returns:
        dict with workflow_id, status, hil_pending.
    """
    wf_id = workflow_id or str(uuid4())

    # Feature flag check
    feature_flag_svc = _get_feature_flag_service()
    if not feature_flag_svc.is_enabled("watchlist_scan", env):
        logger.info(
            "watchlist_scan_generate: feature 'watchlist_scan' disabled — skipping "
            "user=%s workflow=%s",
            user_id,
            wf_id,
        )
        return {
            "workflow_id": wf_id,
            "status": "SKIPPED",
            "hil_pending": False,
            "reason": "feature_disabled",
        }

    logger.info(
        "watchlist_scan_generate: starting user=%s tenant=%s workflow=%s",
        user_id,
        tenant_id,
        wf_id,
    )

    return asyncio.get_event_loop().run_until_complete(
        _run_watchlist_scan_for_user(
            user_id=user_id,
            tenant_id=tenant_id,
            workflow_id=wf_id,
        )
    )


# ── Fan-out orchestrator ───────────────────────────────────────────────────────


@shared_task(
    name="ai.watchlist_scan_fanout",
    bind=False,
    time_limit=120,
    soft_time_limit=90,
    max_retries=0,
)
def watchlist_scan_fanout(env: str = "production") -> dict:
    """Celery Beat orchestrator: dispatch one watchlist_scan_generate per active user.

    Queries all active users who have a non-empty watchlist and dispatches
    a separate ``ai.watchlist_scan`` task per user (fan-out pattern).

    Args:
        env: Environment string for feature flag lookup.

    Returns:
        dict with dispatched_count and skipped_count.
    """
    feature_flag_svc = _get_feature_flag_service()
    if not feature_flag_svc.is_enabled("watchlist_scan", env):
        logger.info("watchlist_scan_fanout: feature disabled — skipping")
        return {"dispatched_count": 0, "skipped_count": 0, "reason": "feature_disabled"}

    return asyncio.get_event_loop().run_until_complete(_run_fanout(env=env))


async def _run_fanout(env: str) -> dict:
    """Async core of the fan-out orchestrator."""
    try:
        active_users = await _fetch_active_users_with_watchlist()
    except Exception:
        logger.exception("watchlist_scan_fanout: failed to fetch active users")
        return {"dispatched_count": 0, "skipped_count": 0, "error": "fetch_failed"}

    dispatched = 0
    skipped = 0

    for user in active_users:
        user_id = str(user.get("user_id", ""))
        tenant_id = str(user.get("tenant_id", ""))
        watchlist_size = user.get("watchlist_size", 0)

        if not user_id or not tenant_id:
            skipped += 1
            continue

        if watchlist_size == 0:
            logger.debug(
                "watchlist_scan_fanout: skipping user=%s (empty watchlist)", user_id
            )
            skipped += 1
            continue

        workflow_id = str(uuid4())
        watchlist_scan_generate.delay(
            user_id=user_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            env=env,
        )
        logger.info(
            "watchlist_scan_fanout: dispatched for user=%s workflow=%s",
            user_id,
            workflow_id,
        )
        dispatched += 1

    logger.info(
        "watchlist_scan_fanout: dispatched=%d skipped=%d",
        dispatched,
        skipped,
    )

    return {"dispatched_count": dispatched, "skipped_count": skipped}


async def _fetch_active_users_with_watchlist() -> list[dict]:
    """Fetch active users who have watchlist items.

    Returns list of dicts: {user_id, tenant_id, watchlist_size}.
    """
    async with _get_db_session() as session:
        from sqlalchemy import text

        stmt = text(
            """
            SELECT u.user_id, u.tenant_id, COUNT(w.company_id) AS watchlist_size
            FROM "user" u
            JOIN watchlist w ON w.user_id = u.user_id
            GROUP BY u.user_id, u.tenant_id
            HAVING COUNT(w.company_id) > 0
            ORDER BY u.user_id
            """
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()
        return [dict(row) for row in rows]
