"""Integration tests for the geo-modifier end-to-end flow.

Exercises the full geo-modifier pathway using in-memory fakes (no real DB).
Tests can be run without a live database — DATABASE_URL is not required.

PLAN-F-018 TASK-009
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.storage.interfaces.i_event_exposure_repository import ExposureRow
from src.scoring.schemas.indicator import IndicatorRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.repositories.interfaces import GeoAdjustedUpdate
from src.scoring.schemas.geo_modifier import GeoModifierPayload

pytestmark = pytest.mark.integration

TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------

def _make_indicator(*, tenant_id=TENANT_ID, geo_weight=0.8, indicator_id=None) -> IndicatorRecord:
    return IndicatorRecord(
        indicator_id=indicator_id or uuid4(),
        tenant_id=tenant_id,
        name="Test Indicator",
        formula_dsl="revenue",
        normalization_mode="percentile",
        normalization_config={},
        direction="higher_better",
        geo_weight=geo_weight,
        version=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_score_record(
    *,
    company_id,
    indicator_id,
    tenant_id=TENANT_ID,
    score=70.0,
    geo_adjusted=None,
) -> CompanyScoreRecord:
    return CompanyScoreRecord(
        score_id=uuid4(),
        company_id=company_id,
        indicator_id=indicator_id,
        tenant_id=tenant_id,
        raw_value=score,
        score=score,
        percentile=50.0,
        geo_adjusted=geo_adjusted,
        inputs_hash="abc123",
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class _InMemoryExposureRepo:
    def __init__(self, rows):
        self._rows = rows

    async def get_by_event(self, event_id, tenant_id):
        return self._rows

    async def bulk_insert(self, event_id, candidates):
        pass


class _InMemoryIndicatorRepo:
    def __init__(self, indicators):
        self._indicators = indicators

    async def list_by_tenant(self, tenant_id):
        return [i for i in self._indicators if i.tenant_id == tenant_id]

    async def get_by_id(self, indicator_id, tenant_id):
        for i in self._indicators:
            if i.indicator_id == indicator_id and i.tenant_id == tenant_id:
                return i
        return None

    async def save(self, record): return record
    async def get_version(self, *a): return None
    async def list_versions(self, *a): return []


class _InMemoryScoreRepo:
    """Tracks writes as a list; supports querying latest per (company, indicator)."""

    def __init__(self, initial_rows=None):
        self._rows: list[CompanyScoreRecord] = list(initial_rows or [])
        self._written: list[CompanyScoreRecord] = []

    async def get_current(self, company_id, indicator_id):
        matches = [
            r for r in self._rows
            if r.company_id == company_id and r.indicator_id == indicator_id
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda r: r.computed_at, reverse=True)[0]

    async def upsert_if_changed(self, record): return True

    async def get_history(self, *a): return []

    async def bulk_update_geo_adjusted(self, updates):
        """Write new snapshot rows for each update that passes epsilon guard."""
        from src.scoring.repositories.company_score_repo import SCORE_CHANGE_EPSILON

        inserted = 0
        for upd in updates:
            current = await self.get_current(upd.company_id, upd.indicator_id)
            if current is None:
                continue
            prev_geo = current.geo_adjusted if current.geo_adjusted is not None else 0.0
            if abs(upd.geo_adjusted - prev_geo) <= SCORE_CHANGE_EPSILON:
                continue
            new_row = CompanyScoreRecord(
                score_id=uuid4(),
                company_id=upd.company_id,
                indicator_id=upd.indicator_id,
                tenant_id=current.tenant_id,
                raw_value=current.raw_value,
                score=current.score,
                percentile=current.percentile,
                geo_adjusted=upd.geo_adjusted,
                inputs_hash=current.inputs_hash,
                computed_at=upd.computed_at,
            )
            self._rows.append(new_row)
            self._written.append(new_row)
            inserted += 1
        return inserted


class _InMemoryCompanyRepo:
    def __init__(self, ticker_map):
        self._map = ticker_map

    async def get_tickers_by_ids(self, ids):
        return {cid: self._map.get(cid, "") for cid in ids}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeoModifierIntegration:

    @pytest.mark.asyncio
    async def test_company_a_and_b_geo_adjusted_updated_company_c_untouched(self):
        """Two exposed companies have geo_adjusted updated; company C (not in exposure) has no new row."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()
        company_b = uuid4()
        company_c = uuid4()  # NOT in exposure set

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.6),
            ExposureRow(company_id=company_b, exposure_type="geo", direction="negative", magnitude=0.3),
        ]

        indicator = _make_indicator(geo_weight=0.8, indicator_id=indicator_id)

        initial_rows = [
            _make_score_record(company_id=company_a, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0),
            _make_score_record(company_id=company_b, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0),
            _make_score_record(company_id=company_c, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0),
        ]

        exposure_repo = _InMemoryExposureRepo(exposures)
        indicator_repo = _InMemoryIndicatorRepo([indicator])
        score_repo = _InMemoryScoreRepo(initial_rows)
        company_repo = _InMemoryCompanyRepo({company_a: "AAPL", company_b: "MSFT", company_c: "GOOG"})

        payloads = []
        async def capture_broadcast(payload, tenant_id):
            payloads.append(payload)

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=TENANT_ID,
            exposure_repo=exposure_repo,
            indicator_repo=indicator_repo,
            score_repo=score_repo,
            company_repo=company_repo,
            broadcaster=capture_broadcast,
        )

        assert result["companies_updated"] == 2

        # company_a: new geo_adjusted row
        a_rows = [r for r in score_repo._rows if r.company_id == company_a]
        assert len(a_rows) == 2
        new_a = max(a_rows, key=lambda r: r.computed_at)
        assert new_a.geo_adjusted != 70.0

        # company_b: new geo_adjusted row
        b_rows = [r for r in score_repo._rows if r.company_id == company_b]
        assert len(b_rows) == 2
        new_b = max(b_rows, key=lambda r: r.computed_at)
        assert new_b.geo_adjusted != 70.0

        # company_c: untouched — still only one row
        c_rows = [r for r in score_repo._rows if r.company_id == company_c]
        assert len(c_rows) == 1

    @pytest.mark.asyncio
    async def test_company_a_clamped_to_100(self):
        """geo_adjusted = 70 * (1 + 0.8 * 0.6 * 1) = 103.6 → clamped to 100.0."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.6),
        ]
        indicator = _make_indicator(geo_weight=0.8, indicator_id=indicator_id)
        initial_rows = [
            _make_score_record(company_id=company_a, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0),
        ]

        score_repo = _InMemoryScoreRepo(initial_rows)

        async def noop_broadcast(payload, tenant_id): pass

        await _run_geo_modifier(
            event_id=event_id,
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo,
            company_repo=_InMemoryCompanyRepo({company_a: "AAPL"}),
            broadcaster=noop_broadcast,
        )

        # Expected without clamping: 70 * (1 + 0.8 * 0.6 * 1) = 103.6, clamped to 100.0
        new_rows = [r for r in score_repo._rows if r.company_id == company_a and r.geo_adjusted != 70.0]
        assert len(new_rows) == 1
        assert new_rows[0].geo_adjusted == 100.0

    @pytest.mark.asyncio
    async def test_company_b_geo_adjusted_equals_53_2(self):
        """geo_adjusted = 70 * (1 + 0.8 * 0.3 * -1) = 70 * 0.76 = 53.2."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        indicator_id = uuid4()
        company_b = uuid4()

        exposures = [
            ExposureRow(company_id=company_b, exposure_type="geo", direction="negative", magnitude=0.3),
        ]
        indicator = _make_indicator(geo_weight=0.8, indicator_id=indicator_id)
        initial_rows = [
            _make_score_record(company_id=company_b, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0),
        ]
        score_repo = _InMemoryScoreRepo(initial_rows)

        async def noop_broadcast(payload, tenant_id): pass

        await _run_geo_modifier(
            event_id=event_id,
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo,
            company_repo=_InMemoryCompanyRepo({company_b: "MSFT"}),
            broadcaster=noop_broadcast,
        )

        # 70 * (1 - 0.8 * 0.3) = 70 * 0.76 = 53.2
        new_rows = [r for r in score_repo._rows if r.company_id == company_b and r.geo_adjusted is not None and abs(r.geo_adjusted - 53.2) < 0.001]
        assert len(new_rows) == 1

    @pytest.mark.asyncio
    async def test_intensity_5_vs_1_score_delta_measurably_larger(self):
        """AC-004: higher magnitude (intensity-5 proxy) produces larger score_delta."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        indicator_id = uuid4()
        company_high = uuid4()
        company_low = uuid4()

        # magnitude=0.8 ~ intensity-5; magnitude=0.16 ~ intensity-1 (same geo_revenue fraction)
        exposures_high = [
            ExposureRow(company_id=company_high, exposure_type="geo", direction="positive", magnitude=0.8),
        ]
        exposures_low = [
            ExposureRow(company_id=company_low, exposure_type="geo", direction="positive", magnitude=0.16),
        ]
        indicator = _make_indicator(geo_weight=0.8, indicator_id=indicator_id)

        score_high = _make_score_record(company_id=company_high, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0)
        score_low = _make_score_record(company_id=company_low, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0)

        payloads_high = []
        payloads_low = []

        async def capture_high(payload, tenant_id): payloads_high.append(payload)
        async def capture_low(payload, tenant_id): payloads_low.append(payload)

        score_repo_high = _InMemoryScoreRepo([score_high])
        await _run_geo_modifier(
            event_id=uuid4(),
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures_high),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo_high,
            company_repo=_InMemoryCompanyRepo({company_high: "AAPL"}),
            broadcaster=capture_high,
        )

        score_repo_low = _InMemoryScoreRepo([score_low])
        await _run_geo_modifier(
            event_id=uuid4(),
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures_low),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo_low,
            company_repo=_InMemoryCompanyRepo({company_low: "MSFT"}),
            broadcaster=capture_low,
        )

        assert len(payloads_high) == 1
        assert len(payloads_low) == 1

        delta_high = abs(payloads_high[0].affected_companies[0].score_delta)
        delta_low = abs(payloads_low[0].affected_companies[0].score_delta)

        assert delta_high > delta_low, (
            f"Expected intensity-5 delta ({delta_high:.3f}) > intensity-1 delta ({delta_low:.3f})"
        )

    @pytest.mark.asyncio
    async def test_rerunning_same_event_produces_no_new_rows(self):
        """Re-running task with identical inputs → epsilon guard fires → 0 new rows written."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        # Compute what the first run will produce
        # base=70, geo_weight=0.8, magnitude=0.3, direction=negative
        # geo_adjusted = 70 * (1 - 0.8 * 0.3) = 53.2
        expected_geo = 70.0 * (1.0 - 0.8 * 0.3)  # 53.2

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="negative", magnitude=0.3),
        ]
        indicator = _make_indicator(geo_weight=0.8, indicator_id=indicator_id)

        # Seed with the already-computed value to simulate a prior run
        initial_rows = [
            _make_score_record(company_id=company_a, indicator_id=indicator_id, score=70.0, geo_adjusted=expected_geo),
        ]
        score_repo = _InMemoryScoreRepo(initial_rows)
        written_before = len(score_repo._rows)

        async def noop_broadcast(payload, tenant_id): pass

        result = await _run_geo_modifier(
            event_id=event_id,
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo,
            company_repo=_InMemoryCompanyRepo({company_a: "AAPL"}),
            broadcaster=noop_broadcast,
        )

        # Epsilon guard: no new rows written because computed value == existing value
        assert result["companies_updated"] == 0
        assert len(score_repo._rows) == written_before

    @pytest.mark.asyncio
    async def test_200_companies_completes_within_5_seconds(self):
        """Performance: 200 companies × 1 indicator completes in < 5 seconds."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        indicator_id = uuid4()
        indicator = _make_indicator(geo_weight=0.5, indicator_id=indicator_id)

        company_ids = [uuid4() for _ in range(200)]
        exposures = [
            ExposureRow(company_id=cid, exposure_type="geo", direction="positive", magnitude=0.5)
            for cid in company_ids
        ]
        initial_rows = [
            _make_score_record(company_id=cid, indicator_id=indicator_id, score=70.0, geo_adjusted=70.0)
            for cid in company_ids
        ]
        score_repo = _InMemoryScoreRepo(initial_rows)
        ticker_map = {cid: f"T{i}" for i, cid in enumerate(company_ids)}

        async def noop_broadcast(payload, tenant_id): pass

        start = time.monotonic()
        result = await _run_geo_modifier(
            event_id=uuid4(),
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo,
            company_repo=_InMemoryCompanyRepo(ticker_map),
            broadcaster=noop_broadcast,
        )
        elapsed = time.monotonic() - start

        assert result["companies_updated"] == 200
        assert elapsed < 5.0, f"Geo-modifier took {elapsed:.2f}s — exceeds 5s SLA"

    @pytest.mark.asyncio
    async def test_broadcast_payload_shape_correct(self):
        """GeoModifierPayload has correct structure (AC-002 shape assertion)."""
        from src.scoring.geo_modifier_worker import _run_geo_modifier

        event_id = uuid4()
        indicator_id = uuid4()
        company_a = uuid4()

        exposures = [
            ExposureRow(company_id=company_a, exposure_type="geo", direction="positive", magnitude=0.4),
        ]
        indicator = _make_indicator(geo_weight=0.5, indicator_id=indicator_id)
        initial_rows = [
            _make_score_record(company_id=company_a, indicator_id=indicator_id, score=80.0, geo_adjusted=80.0),
        ]
        score_repo = _InMemoryScoreRepo(initial_rows)

        captured: list[GeoModifierPayload] = []

        async def capture_broadcast(payload, tenant_id):
            captured.append(payload)

        await _run_geo_modifier(
            event_id=event_id,
            tenant_id=TENANT_ID,
            exposure_repo=_InMemoryExposureRepo(exposures),
            indicator_repo=_InMemoryIndicatorRepo([indicator]),
            score_repo=score_repo,
            company_repo=_InMemoryCompanyRepo({company_a: "AAPL"}),
            broadcaster=capture_broadcast,
        )

        assert len(captured) == 1
        payload = captured[0]
        assert payload.event_id == event_id
        assert len(payload.affected_companies) == 1
        delta = payload.affected_companies[0]
        assert delta.company_id == company_a
        assert delta.ticker == "AAPL"
        # 80 * (1 + 0.5 * 0.4 * 1) = 96.0
        assert abs(delta.new_geo_adjusted - 96.0) < 0.001
        assert abs(delta.score_delta - 16.0) < 0.001
