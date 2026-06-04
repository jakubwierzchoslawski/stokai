"""
tests.unit.portfolio.test_csv_import_service

Unit tests for CsvImportService using stub repositories and company lookup.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from src.portfolio.csv_import_service import CsvImportService, CsvRowError
from src.portfolio.exceptions import ValidationError
from src.storage.models.portfolio import Position


# ── Stubs ──────────────────────────────────────────────────────────────────────


class _StubPositionRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def bulk_create(self, tenant_id, portfolio_id, rows) -> list[Position]:
        result = []
        for row in rows:
            pos = Position(
                position_id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                company_id=row["company_id"],
                ticker=row["ticker"],
                shares=row["shares"],
                cost_basis=row.get("cost_basis"),
                source=row.get("source", "csv"),
                added_at=datetime.utcnow(),
            )
            self.created.append(row)
            result.append(pos)
        return result


class _StubCompanyLookup:
    def __init__(self, ticker_map: dict[str, uuid.UUID]) -> None:
        self._map = ticker_map

    async def resolve_ticker(self, ticker: str) -> uuid.UUID | None:
        return self._map.get(ticker)


def _make_service(
    ticker_map: dict[str, uuid.UUID] | None = None,
) -> tuple[CsvImportService, _StubPositionRepo]:
    repo = _StubPositionRepo()
    company_ids = ticker_map or {
        "AAPL": uuid.uuid4(),
        "MSFT": uuid.uuid4(),
        "TSLA": uuid.uuid4(),
    }
    svc = CsvImportService(repo, _StubCompanyLookup(company_ids))
    return svc, repo


def _csv(rows: list[str], header: str = "ticker,shares,cost_basis") -> bytes:
    lines = [header] + rows
    return "\n".join(lines).encode()


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_all_valid():
    """3 valid rows → positions_created=3, errors=[]."""
    svc, repo = _make_service()
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    csv_bytes = _csv([
        "AAPL,10,150.0",
        "MSFT,5,300.0",
        "TSLA,3,",
    ])

    result = await svc.import_csv(tid, pid, csv_bytes)
    assert result.positions_created == 3
    assert result.errors == []
    assert len(repo.created) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_partial_errors():
    """Row 2 has invalid shares → positions_created=2, errors=[{row_number:3}].

    Note: row_number is 1-indexed from the data (header=row 1, data starts at 2).
    """
    svc, repo = _make_service()
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    csv_bytes = _csv([
        "AAPL,10,150.0",
        "MSFT,INVALID,300.0",  # row 3 (header is row 1, AAPL is row 2)
        "TSLA,3,",
    ])

    result = await svc.import_csv(tid, pid, csv_bytes)
    assert result.positions_created == 2
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3
    assert result.errors[0].ticker == "MSFT"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_unresolvable_ticker():
    """Unresolvable ticker produces a row error; other rows succeed."""
    ticker_map = {"AAPL": uuid.uuid4(), "TSLA": uuid.uuid4()}
    svc, repo = _make_service(ticker_map)
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    csv_bytes = _csv([
        "AAPL,10,",
        "UNKNOWN_TICKER,5,",
        "TSLA,3,",
    ])

    result = await svc.import_csv(tid, pid, csv_bytes)
    assert result.positions_created == 2
    assert len(result.errors) == 1
    assert result.errors[0].ticker == "UNKNOWN_TICKER"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_exceeds_limit():
    """501 rows → ValidationError raised before any insert."""
    svc, repo = _make_service()
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    rows = [f"AAPL,{i}," for i in range(1, 502)]  # 501 data rows
    csv_bytes = _csv(rows)

    with pytest.raises(ValidationError, match="500"):
        await svc.import_csv(tid, pid, csv_bytes)

    assert repo.created == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_missing_required_column():
    """CSV without 'ticker' column → ValidationError before processing rows."""
    svc, repo = _make_service()
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    csv_bytes = _csv(["10,150.0", "5,300.0"], header="shares,cost_basis")

    with pytest.raises(ValidationError, match="ticker"):
        await svc.import_csv(tid, pid, csv_bytes)

    assert repo.created == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_csv_import_cost_basis_optional():
    """Empty cost_basis column → Position(cost_basis=None)."""
    svc, repo = _make_service()
    tid = uuid.uuid4()
    pid = uuid.uuid4()

    csv_bytes = _csv(["AAPL,10,"])

    result = await svc.import_csv(tid, pid, csv_bytes)
    assert result.positions_created == 1
    assert result.errors == []
    assert repo.created[0]["cost_basis"] is None
