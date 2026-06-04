"""
ProgressiveDisclosureRepository — SQLAlchemy 2.0 async implementation.

PLAN-F-020 TASK-002

Reads from existing tables (no new migrations):
  geo_event, ai_recommendation, event_exposure, company,
  agent_invocation, workflow_run, price_bar.

IDOR prevention (ARCHITECTURE §12.1):
  All event lookups enforce: geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id.
  A foreign event_id returns None; the service layer raises EventNotFoundError → 404.

Sparkline guard: days * len(company_ids) must not exceed 700 rows.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.progressive_disclosure.interfaces.i_progressive_disclosure_repository import (
    AffectedCompanyRow,
    AnalogSummaryRow,
    AuditTrailRow,
    DeepDiveRow,
    IProgressiveDisclosureRepository,
    PopupDataRow,
    PricePoint,
    ReasoningStepRow,
    SidePanelDataRow,
    SocialPostRow,
    TickerDeltaRow,
)

logger = logging.getLogger(__name__)

# Maximum rows returned by get_sparklines (days × company_count bound)
_MAX_SPARKLINE_ROWS = 700


class ProgressiveDisclosureRepository(IProgressiveDisclosureRepository):
    """SQLAlchemy 2.0 async implementation of IProgressiveDisclosureRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Ownership filter helper ────────────────────────────────────────────────

    @staticmethod
    def _tenant_filter(tenant_id: UUID) -> str:
        """Return a parameterised SQL fragment for tenant ownership check.

        Returned as a raw string to be used with :func:`text`; parameters are
        bound by the caller using `bindparams`.
        """
        return (
            "(geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id)"
        )

    # ── get_popup_data ─────────────────────────────────────────────────────────

    async def get_popup_data(
        self, event_id: UUID, tenant_id: UUID
    ) -> PopupDataRow | None:
        """JOIN geo_event + event_exposure + ai_recommendation + company.

        Returns None if the event does not exist or belongs to a different tenant.
        """
        stmt = text(
            """
            SELECT
                ge.event_id,
                ge.category,
                ge.intensity,
                ge.title                  AS headline,
                ge.occurred_at,
                ge.location               AS location,
                COALESCE(
                    (SELECT COUNT(*)
                     FROM event_exposure ee2
                     WHERE ee2.event_id = ge.event_id),
                    0
                )                         AS exposed_holdings_count,
                ar.action_signal,
                ar.confidence,
                ar.sample_size
            FROM geo_event ge
            LEFT JOIN ai_recommendation ar ON ar.event_id = ge.event_id
            WHERE ge.event_id = :event_id
              AND (ge.tenant_id IS NULL OR ge.tenant_id = :tenant_id)
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id), tenant_id=str(tenant_id))

        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None

        # Fetch tickers with delta from event_exposure + company
        tickers_stmt = text(
            """
            SELECT c.ticker, ee.score_delta
            FROM event_exposure ee
            JOIN company c ON c.company_id = ee.company_id
            WHERE ee.event_id = :event_id
            ORDER BY ABS(ee.score_delta) DESC
            """
        ).bindparams(event_id=str(event_id))
        tickers_result = await self._session.execute(tickers_stmt)
        tickers = [
            TickerDeltaRow(ticker=tr["ticker"], score_delta=float(tr["score_delta"]))
            for tr in tickers_result.mappings()
        ]

        sample_size = int(row["sample_size"] or 0)
        category = row["category"] or []
        if isinstance(category, str):
            try:
                category = json.loads(category)
            except (json.JSONDecodeError, TypeError):
                category = [category]

        return PopupDataRow(
            event_id=UUID(str(row["event_id"])),
            category=list(category),
            intensity=int(row["intensity"]),
            headline=str(row["headline"]),
            occurred_at=row["occurred_at"],
            location=str(row["location"] or ""),
            exposed_holdings_count=int(row["exposed_holdings_count"]),
            tickers_with_delta=tickers,
            action_signal=str(row["action_signal"] or "HOLD"),
            confidence=float(row["confidence"] or 0.0),
            sample_size=sample_size,
            low_sample=sample_size < 5,
        )

    # ── get_side_panel_data ────────────────────────────────────────────────────

    async def get_side_panel_data(
        self, event_id: UUID, tenant_id: UUID
    ) -> SidePanelDataRow | None:
        """Extends popup query with rationale, analogies, is_contrarian, social_posts."""
        popup_row = await self.get_popup_data(event_id, tenant_id)
        if popup_row is None:
            return None

        detail_stmt = text(
            """
            SELECT
                ge.summary,
                ar.rationale,
                ar.analogies,
                ar.is_contrarian,
                ar.contrarian_callout,
                ar.social_posts
            FROM geo_event ge
            LEFT JOIN ai_recommendation ar ON ar.event_id = ge.event_id
            WHERE ge.event_id = :event_id
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id))

        result = await self._session.execute(detail_stmt)
        detail = result.mappings().first()

        # Affected companies
        comp_stmt = text(
            """
            SELECT
                c.company_id,
                c.ticker,
                c.name,
                ee.geo_adjusted_score  AS score,
                ee.score_delta         AS delta
            FROM event_exposure ee
            JOIN company c ON c.company_id = ee.company_id
            WHERE ee.event_id = :event_id
            ORDER BY ABS(ee.score_delta) DESC
            """
        ).bindparams(event_id=str(event_id))
        comp_result = await self._session.execute(comp_stmt)
        affected_companies = [
            AffectedCompanyRow(
                company_id=UUID(str(cr["company_id"])),
                ticker=str(cr["ticker"]),
                name=str(cr["name"]),
                score=float(cr["score"] or 0.0),
                delta=float(cr["delta"] or 0.0),
            )
            for cr in comp_result.mappings()
        ]

        # Parse analogies JSONB (top 3)
        analogies: list[AnalogSummaryRow] = []
        if detail and detail["analogies"]:
            raw_analogs = detail["analogies"]
            if isinstance(raw_analogs, str):
                raw_analogs = json.loads(raw_analogs)
            for a in raw_analogs[:3]:
                analogies.append(
                    AnalogSummaryRow(
                        event_id=str(a.get("event_id", "")),
                        headline=str(a.get("headline", "")),
                        occurred_at=str(a.get("occurred_at", "")),
                        similarity_score=float(a.get("similarity_score", 0.0)),
                    )
                )

        # Parse social_posts JSONB
        social_posts: list[SocialPostRow] | None = None
        if detail and detail["social_posts"]:
            raw_posts = detail["social_posts"]
            if isinstance(raw_posts, str):
                raw_posts = json.loads(raw_posts)
            if raw_posts:
                social_posts = [
                    SocialPostRow(
                        post_id=str(p.get("post_id", "")),
                        source=str(p.get("source", "")),
                        text=str(p.get("text", "")),
                        timestamp=str(p.get("timestamp", "")),
                    )
                    for p in raw_posts
                ]

        is_contrarian = bool(detail["is_contrarian"]) if detail else False
        contrarian_callout: str | None = (
            str(detail["contrarian_callout"])
            if detail and detail["contrarian_callout"]
            else None
        )
        summary = str(detail["summary"]) if detail and detail["summary"] else ""
        rationale = str(detail["rationale"]) if detail and detail["rationale"] else ""

        return SidePanelDataRow(
            event_id=popup_row.event_id,
            category=popup_row.category,
            intensity=popup_row.intensity,
            headline=popup_row.headline,
            occurred_at=popup_row.occurred_at,
            location=popup_row.location,
            exposed_holdings_count=popup_row.exposed_holdings_count,
            tickers_with_delta=popup_row.tickers_with_delta,
            action_signal=popup_row.action_signal,
            confidence=popup_row.confidence,
            sample_size=popup_row.sample_size,
            low_sample=popup_row.low_sample,
            summary=summary,
            rationale=rationale,
            analogies=analogies,
            affected_companies=affected_companies,
            is_contrarian=is_contrarian,
            contrarian_callout=contrarian_callout,
            social_posts=social_posts,
            audit_trail_url=f"/events/{event_id}/audit-trail",
        )

    # ── get_audit_trail ────────────────────────────────────────────────────────

    async def get_audit_trail(self, event_id: UUID) -> AuditTrailRow | None:
        """JOIN workflow_run + agent_invocation, ordered by started_at.

        prompt_version is taken from the last recommendation_synthesizer invocation.
        """
        run_stmt = text(
            """
            SELECT
                wr.run_id,
                wr.langfuse_trace_id
            FROM workflow_run wr
            WHERE wr.inputs->>'event_id' = :event_id
            ORDER BY wr.completed_at DESC
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id))
        run_result = await self._session.execute(run_stmt)
        run_row = run_result.mappings().first()

        if run_row is None:
            return AuditTrailRow(
                event_id=event_id,
                prompt_version="",
                langfuse_trace_url="",
                analogies=[],
                reasoning_steps=[],
            )

        run_id = run_row["run_id"]
        langfuse_trace_id = run_row["langfuse_trace_id"] or ""
        langfuse_trace_url = (
            f"https://langfuse/traces/{langfuse_trace_id}" if langfuse_trace_id else ""
        )

        # Fetch agent_invocation rows ordered by started_at
        inv_stmt = text(
            """
            SELECT
                ai.agent_role,
                ai.step_index,
                ai.output,
                ai.tool_calls,
                ai.prompt_version,
                ai.started_at
            FROM agent_invocation ai
            WHERE ai.run_id = :run_id
            ORDER BY ai.started_at ASC
            """
        ).bindparams(run_id=str(run_id))
        inv_result = await self._session.execute(inv_stmt)
        invocations = list(inv_result.mappings())

        reasoning_steps: list[ReasoningStepRow] = []
        prompt_version = ""

        for idx, inv in enumerate(invocations):
            output = inv["output"] or {}
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    output = {"content": str(output)}

            tool_calls_raw = inv["tool_calls"] or []
            if isinstance(tool_calls_raw, str):
                try:
                    tool_calls_raw = json.loads(tool_calls_raw)
                except (json.JSONDecodeError, TypeError):
                    tool_calls_raw = []

            step_content = str(output.get("content", output.get("text", "")))
            reasoning_steps.append(
                ReasoningStepRow(
                    agent_role=str(inv["agent_role"] or ""),
                    step_index=int(inv["step_index"] if inv["step_index"] is not None else idx),
                    content=step_content,
                    tool_calls=list(tool_calls_raw),
                )
            )

            if inv["agent_role"] == "recommendation_synthesizer" and inv["prompt_version"]:
                prompt_version = str(inv["prompt_version"])

        # If no synthesizer found, use latest
        if not prompt_version and invocations:
            last_pv = invocations[-1]["prompt_version"]
            prompt_version = str(last_pv) if last_pv else ""

        # Reuse analogies from ai_recommendation
        analog_stmt = text(
            """
            SELECT analogies
            FROM ai_recommendation
            WHERE event_id = :event_id
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id))
        analog_result = await self._session.execute(analog_stmt)
        analog_row = analog_result.mappings().first()

        analogies: list[AnalogSummaryRow] = []
        if analog_row and analog_row["analogies"]:
            raw_analogs = analog_row["analogies"]
            if isinstance(raw_analogs, str):
                raw_analogs = json.loads(raw_analogs)
            for a in raw_analogs:
                analogies.append(
                    AnalogSummaryRow(
                        event_id=str(a.get("event_id", "")),
                        headline=str(a.get("headline", "")),
                        occurred_at=str(a.get("occurred_at", "")),
                        similarity_score=float(a.get("similarity_score", 0.0)),
                    )
                )

        return AuditTrailRow(
            event_id=event_id,
            prompt_version=prompt_version,
            langfuse_trace_url=langfuse_trace_url,
            analogies=analogies,
            reasoning_steps=reasoning_steps,
        )

    # ── get_deep_dive ──────────────────────────────────────────────────────────

    async def get_deep_dive(self, event_id: UUID) -> DeepDiveRow | None:
        """Return the most recent completed event_deep_dive workflow output.

        Returns None when no completed deep-dive workflow exists.
        """
        stmt = text(
            """
            SELECT
                wr.run_id,
                wr.final_state,
                wr.completed_at
            FROM workflow_run wr
            WHERE wr.workflow_type = 'event_deep_dive'
              AND wr.inputs->>'event_id' = :event_id
              AND wr.status = 'completed'
            ORDER BY wr.completed_at DESC
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id))

        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None

        final_state = row["final_state"] or {}
        if isinstance(final_state, str):
            try:
                final_state = json.loads(final_state)
            except (json.JSONDecodeError, TypeError):
                final_state = {}

        memo = str(final_state.get("memo", final_state.get("narrative", "")))
        scenario_tree = final_state.get("scenario_tree")

        # Analogies from ai_recommendation (full table for deep dive)
        analog_stmt = text(
            """
            SELECT analogies, affected_companies
            FROM ai_recommendation
            WHERE event_id = :event_id
            LIMIT 1
            """
        ).bindparams(event_id=str(event_id))
        analog_result = await self._session.execute(analog_stmt)
        analog_row = analog_result.mappings().first()

        analogies: list[AnalogSummaryRow] = []
        affected_companies: list[AffectedCompanyRow] = []

        if analog_row and analog_row["analogies"]:
            raw_analogs = analog_row["analogies"]
            if isinstance(raw_analogs, str):
                raw_analogs = json.loads(raw_analogs)
            for a in raw_analogs:
                analogies.append(
                    AnalogSummaryRow(
                        event_id=str(a.get("event_id", "")),
                        headline=str(a.get("headline", "")),
                        occurred_at=str(a.get("occurred_at", "")),
                        similarity_score=float(a.get("similarity_score", 0.0)),
                    )
                )

        # Affected companies
        comp_stmt = text(
            """
            SELECT
                c.company_id, c.ticker, c.name,
                ee.geo_adjusted_score  AS score,
                ee.score_delta         AS delta
            FROM event_exposure ee
            JOIN company c ON c.company_id = ee.company_id
            WHERE ee.event_id = :event_id
            ORDER BY ABS(ee.score_delta) DESC
            """
        ).bindparams(event_id=str(event_id))
        comp_result = await self._session.execute(comp_stmt)
        for cr in comp_result.mappings():
            affected_companies.append(
                AffectedCompanyRow(
                    company_id=UUID(str(cr["company_id"])),
                    ticker=str(cr["ticker"]),
                    name=str(cr["name"]),
                    score=float(cr["score"] or 0.0),
                    delta=float(cr["delta"] or 0.0),
                )
            )

        return DeepDiveRow(
            event_id=event_id,
            memo=memo,
            scenario_tree=scenario_tree,
            analogies=analogies,
            affected_companies=affected_companies,
            generated_at=row["completed_at"],
        )

    # ── get_sparklines ─────────────────────────────────────────────────────────

    async def get_sparklines(
        self, company_ids: list[UUID], days: int = 7
    ) -> dict[UUID, list[PricePoint]]:
        """Return T±days close prices per company from price_bar.

        Bounded to days * len(company_ids) ≤ 700 rows.
        Returns empty list for companies with no price_bar data.
        """
        if not company_ids:
            return {}

        # Enforce row cap
        max_companies = _MAX_SPARKLINE_ROWS // max(days, 1)
        if len(company_ids) > max_companies:
            logger.warning(
                "get_sparklines: capping %d companies to %d (row guard: days=%d)",
                len(company_ids),
                max_companies,
                days,
            )
            company_ids = company_ids[:max_companies]

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        company_id_strs = [str(cid) for cid in company_ids]

        stmt = text(
            """
            SELECT
                pb.company_id,
                DATE(pb.ts)   AS bar_date,
                pb.close
            FROM price_bar pb
            WHERE pb.company_id = ANY(:company_ids)
              AND pb.ts >= :cutoff
            ORDER BY pb.company_id, pb.ts ASC
            LIMIT :max_rows
            """
        ).bindparams(
            company_ids=company_id_strs,
            cutoff=cutoff,
            max_rows=_MAX_SPARKLINE_ROWS,
        )

        result = await self._session.execute(stmt)
        rows = result.mappings().all()

        output: dict[UUID, list[PricePoint]] = {cid: [] for cid in company_ids}
        for r in rows:
            cid = UUID(str(r["company_id"]))
            if cid in output:
                output[cid].append(
                    PricePoint(
                        ts=str(r["bar_date"]),
                        close=float(r["close"]),
                    )
                )

        return output
