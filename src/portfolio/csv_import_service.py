"""
portfolio.csv_import_service — CsvImportService.

Parses a CSV payload (bytes or file-like), validates rows, resolves tickers,
and bulk-inserts valid positions. Partial errors are collected and returned in
CsvImportResult — the import does not fail-fast on individual bad rows.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel

from src.portfolio.exceptions import ValidationError
from src.portfolio.interfaces import ICompanyLookup, IPositionRepository

MAX_ROWS = 500
REQUIRED_COLUMNS = {"ticker", "shares"}


# ── Result models ─────────────────────────────────────────────────────────────


class CsvRowError(BaseModel):
    """Error reported for a single invalid CSV row."""

    row_number: int
    ticker: str
    error: str


class CsvImportResult(BaseModel):
    """Summary returned after a CSV import attempt."""

    positions_created: int
    errors: list[CsvRowError]


# ── Service ───────────────────────────────────────────────────────────────────


class CsvImportService:
    """Parse, validate, and bulk-insert positions from a CSV payload.

    Dependencies are injected via the constructor (DIP).
    """

    def __init__(
        self,
        position_repo: IPositionRepository,
        company_lookup: ICompanyLookup,
    ) -> None:
        self._position_repo = position_repo
        self._company_lookup = company_lookup

    async def import_csv(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        csv_bytes: bytes,
    ) -> CsvImportResult:
        """Parse *csv_bytes*, validate rows, resolve tickers, and bulk-insert.

        Raises ValidationError when:
        - Required columns (ticker, shares) are missing from the header.
        - Total data rows exceed MAX_ROWS (500).

        For individual row errors (invalid shares, unknown ticker, etc.), a
        CsvRowError is appended and the row is skipped. Valid rows are inserted
        in a single bulk_create call.

        Returns CsvImportResult with counts and per-row errors.
        """
        text = csv_bytes.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        # Validate header
        if reader.fieldnames is None:
            raise ValidationError("CSV file is empty or has no header row")

        fieldnames_lower = {f.strip().lower() for f in reader.fieldnames}
        missing = REQUIRED_COLUMNS - fieldnames_lower
        if missing:
            raise ValidationError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        # Normalise fieldnames to lowercase
        reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]

        rows = list(reader)
        if len(rows) > MAX_ROWS:
            raise ValidationError(
                f"CSV exceeds the maximum of {MAX_ROWS} rows "
                f"(got {len(rows)}). Split the file and re-upload."
            )

        errors: list[CsvRowError] = []
        valid_rows: list[dict] = []

        for row_number, row in enumerate(rows, start=2):  # 1-indexed, row 1 is header
            ticker = (row.get("ticker") or "").strip()
            shares_raw = (row.get("shares") or "").strip()
            cost_basis_raw = (row.get("cost_basis") or "").strip()

            # Validate ticker
            if not ticker:
                errors.append(CsvRowError(
                    row_number=row_number,
                    ticker="",
                    error="ticker is required",
                ))
                continue

            # Validate shares
            try:
                shares = float(shares_raw)
                if shares <= 0:
                    raise ValueError("shares must be positive")
            except (ValueError, TypeError):
                errors.append(CsvRowError(
                    row_number=row_number,
                    ticker=ticker,
                    error=f"invalid shares value: {shares_raw!r}",
                ))
                continue

            # Validate cost_basis (optional)
            cost_basis: float | None = None
            if cost_basis_raw:
                try:
                    cost_basis = float(cost_basis_raw)
                    if cost_basis <= 0:
                        raise ValueError("cost_basis must be positive")
                except (ValueError, TypeError):
                    errors.append(CsvRowError(
                        row_number=row_number,
                        ticker=ticker,
                        error=f"invalid cost_basis value: {cost_basis_raw!r}",
                    ))
                    continue

            # Resolve ticker to company_id
            company_id = await self._company_lookup.resolve_ticker(ticker)
            if company_id is None:
                errors.append(CsvRowError(
                    row_number=row_number,
                    ticker=ticker,
                    error=f"ticker {ticker!r} not found in company registry",
                ))
                continue

            valid_rows.append({
                "company_id": company_id,
                "ticker": ticker,
                "shares": shares,
                "cost_basis": cost_basis,
                "source": "csv",
            })

        # Bulk-insert all valid rows in one transaction slice
        if valid_rows:
            await self._position_repo.bulk_create(tenant_id, portfolio_id, valid_rows)

        return CsvImportResult(
            positions_created=len(valid_rows),
            errors=errors,
        )
