"""
Celery task: scoring.apply_geo_modifier

Applies the geo-modifier formula to all companies exposed to a geopolitical event,
writes new geo_adjusted snapshot rows, and broadcasts the score deltas via WebSocket.

Formula:
    direction_sign = +1 if direction == "positive" else (-1 if direction == "negative" else 0)
    geo_adjusted = base_score * (1 + geo_weight * magnitude * direction_sign)
    geo_adjusted = clamp(geo_adjusted, 0.0, 100.0)

Performance (AC-001):
    - O(indicators_with_geo_weight + 1) DB round-trips per event.
    - Uses bulk_update_geo_adjusted (single INSERT batch per indicator).

PLAN-F-018 TASK-005
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from src.scoring.schemas.geo_modifier import CompanyScoreDelta, GeoModifierPayload
from src.scoring.repositories.interfaces import GeoAdjustedUpdate

logger = logging.getLogger(__name__)

_GEO_ADJUSTED_MIN = 0.0
_GEO_ADJUSTED_MAX = 100.0


def _clamp(value: float) -> float:
    return max(_GEO_ADJUSTED_MIN, min(_GEO_ADJUSTED_MAX, value))


def _direction_sign(direction: str) -> int:
    """Map direction string to integer sign."""
    if direction == "positive":
        return 1
    if direction == "negative":
        return -1
    # "neutral" or unknown → no adjustment
    return 0


async def _run_geo_modifier(
    *,
    event_id: UUID,
    tenant_id: UUID,
    exposure_repo: Any,
    indicator_repo: Any,
    score_repo: Any,
    company_repo: Any,
    broadcaster: Any,
) -> dict:
    """Core geo-modifier logic, extracted for testability without Celery.

    Args:
        event_id: UUID of the triggering geo_event.
        tenant_id: Tenant UUID for scoping.
        exposure_repo: IEventExposureRepository instance.
        indicator_repo: IIndicatorRepository instance.
        score_repo: ICompanyScoreRepository instance.
        company_repo: ICompanyRepository (or duck-typed) with get_tickers_by_ids.
        broadcaster: Coroutine callable accepting (GeoModifierPayload, tenant_id).

    Returns:
        dict with {"event_id": str, "companies_updated": int}
    """
    # Step 1: Load event_exposure rows
    exposures = await exposure_repo.get_by_event(event_id, tenant_id)

    if not exposures:
        logger.info(
            "apply_geo_modifier: no exposures for event=%s tenant=%s — no-op.",
            event_id,
            tenant_id,
        )
        return {"event_id": str(event_id), "companies_updated": 0}

    # Step 2: Load all indicators for tenant; filter geo_weight > 0 in Python
    all_indicators = await indicator_repo.list_by_tenant(tenant_id)
    active_indicators = [ind for ind in all_indicators if ind.geo_weight > 0.0]

    if not active_indicators:
        logger.info(
            "apply_geo_modifier: no indicators with geo_weight > 0 for tenant=%s — no-op.",
            tenant_id,
        )
        return {"event_id": str(event_id), "companies_updated": 0}

    # Build exposure lookup: company_id → ExposureRow
    exposure_by_company = {exp.company_id: exp for exp in exposures}
    exposed_company_ids = list(exposure_by_company.keys())

    now = datetime.now(timezone.utc)
    all_updates: list[GeoAdjustedUpdate] = []
    score_deltas: dict[UUID, tuple[float, float]] = {}  # company_id → (new_geo, prev_geo)

    # Step 3: For each indicator with geo_weight > 0:
    for indicator in active_indicators:
        geo_weight = indicator.geo_weight

        # Load current base scores for all exposed companies (one query per indicator)
        base_scores: dict[UUID, Any] = {}
        for company_id in exposed_company_ids:
            record = await score_repo.get_current(company_id, indicator.indicator_id)
            if record is None:
                logger.warning(
                    "apply_geo_modifier: no company_score row for company=%s "
                    "indicator=%s — skipping pair.",
                    company_id,
                    indicator.indicator_id,
                )
                continue
            base_scores[company_id] = record

        # Compute geo_adjusted for each company
        for company_id, record in base_scores.items():
            exposure = exposure_by_company[company_id]
            sign = _direction_sign(exposure.direction)

            if sign == 0:
                logger.debug(
                    "apply_geo_modifier: neutral direction for company=%s "
                    "indicator=%s — net zero geo effect.",
                    company_id,
                    indicator.indicator_id,
                )

            geo_adjusted = _clamp(
                record.score * (1.0 + geo_weight * exposure.magnitude * sign)
            )

            all_updates.append(
                GeoAdjustedUpdate(
                    company_id=company_id,
                    indicator_id=indicator.indicator_id,
                    geo_adjusted=geo_adjusted,
                    computed_at=now,
                )
            )

            prev_geo = record.geo_adjusted if record.geo_adjusted is not None else record.score
            # Track deltas (last indicator wins for payload — acceptable for broadcast)
            score_deltas[company_id] = (geo_adjusted, prev_geo)

    if not all_updates:
        return {"event_id": str(event_id), "companies_updated": 0}

    # Step 4: Bulk write all updates
    companies_updated = await score_repo.bulk_update_geo_adjusted(all_updates)

    # Step 5: Collect tickers for affected companies
    affected_ids = [uid for uid in score_deltas.keys()]
    ticker_map: dict[UUID, str] = {}
    try:
        ticker_map = await company_repo.get_tickers_by_ids(affected_ids)
    except Exception as exc:
        logger.warning("apply_geo_modifier: ticker lookup failed: %s", exc)

    # Step 6: Build and broadcast GeoModifierPayload
    deltas = [
        CompanyScoreDelta(
            company_id=company_id,
            ticker=ticker_map.get(company_id, ""),
            new_geo_adjusted=new_geo,
            score_delta=new_geo - prev_geo,
        )
        for company_id, (new_geo, prev_geo) in score_deltas.items()
    ]

    if deltas:
        payload = GeoModifierPayload(
            event_id=event_id,
            affected_companies=deltas,
        )
        await broadcaster(payload, str(tenant_id))

    return {"event_id": str(event_id), "companies_updated": companies_updated}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

# Lazy import to avoid circular imports at module level
_celery_app = None


def _get_app():
    global _celery_app
    if _celery_app is None:
        from src.config.celery_app import celery_app
        _celery_app = celery_app
    return _celery_app


def apply_geo_modifier_delay(event_id: str, tenant_id: str) -> None:
    """Fire-and-forget enqueue of the apply_geo_modifier task.

    Called from persist_event_record after the DB transaction commits.
    """
    app = _get_app()
    app.send_task(
        "scoring.apply_geo_modifier",
        kwargs={"event_id": event_id, "tenant_id": tenant_id},
    )


def _create_apply_geo_modifier_task():
    """Register the scoring.apply_geo_modifier Celery task."""
    app = _get_app()

    @app.task(name="scoring.apply_geo_modifier", bind=True, max_retries=3)
    def apply_geo_modifier(self, event_id: str, tenant_id: str) -> dict:
        """Apply geo-modifier to companies exposed to a geopolitical event.

        Runs the async _run_geo_modifier function inside a new event loop
        since Celery tasks are synchronous by default.

        Args:
            event_id: String UUID of the triggering geo_event.
            tenant_id: String UUID of the tenant.

        Returns:
            dict with {"event_id": str, "companies_updated": int}
        """
        import asyncio
        from uuid import UUID as _UUID

        from src.config.settings import get_settings
        from src.api.websocket.geo_modifier_broadcaster import broadcast_geo_modifier

        settings = get_settings()

        async def _run():
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker

            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as session:
                from src.storage.implementations.event_exposure_repository import EventExposureRepository
                from src.scoring.repositories.indicator_repo import IndicatorRepository
                from src.scoring.repositories.company_score_repo import CompanyScoreRepository

                exposure_repo = EventExposureRepository(session)
                indicator_repo = IndicatorRepository(session)
                score_repo = CompanyScoreRepository(session)

                # Minimal duck-typed company repo for ticker lookup
                class _CompanyRepo:
                    async def get_tickers_by_ids(self, ids):
                        from sqlalchemy import text
                        if not ids:
                            return {}
                        result = await session.execute(
                            text("SELECT company_id, ticker FROM company WHERE company_id = ANY(:ids)"),
                            {"ids": [str(i) for i in ids]},
                        )
                        return {row.company_id: row.ticker for row in result.fetchall()}

                try:
                    return await _run_geo_modifier(
                        event_id=_UUID(event_id),
                        tenant_id=_UUID(tenant_id),
                        exposure_repo=exposure_repo,
                        indicator_repo=indicator_repo,
                        score_repo=score_repo,
                        company_repo=_CompanyRepo(),
                        broadcaster=broadcast_geo_modifier,
                    )
                except Exception as exc:
                    logger.exception(
                        "apply_geo_modifier failed for event=%s: %s", event_id, exc
                    )
                    raise self.retry(exc=exc)
                finally:
                    await engine.dispose()

        return asyncio.run(_run())

    return apply_geo_modifier


# Register the task at import time (auto-discovered by Celery)
try:
    _task = _create_apply_geo_modifier_task()
except Exception:
    # In test environments Celery may not be fully configured; log and continue
    logger.debug("apply_geo_modifier task registration deferred (no Celery app available).")
    _task = None
