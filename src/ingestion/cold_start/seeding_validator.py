"""
SeedingValidator — post-seeding health checks.

Verifies that:
1. At least one geo_event row exists from gdelt or acled source providers.
2. event_embedding count matches geo_event count.
3. pgvector cosine query completes in under 2 seconds.
4. At least one event_exposure row has price_change_t1d populated.

Raises SeedingValidationError if any check fails.
Returns ValidationReport with per-check results and timings.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# pgvector cosine query timeout threshold (seconds)
COSINE_QUERY_TIMEOUT_S = 2.0


class SeedingValidationError(Exception):
    """Raised by SeedingValidator.validate() when one or more checks fail."""

    def __init__(self, message: str, report: "ValidationReport") -> None:
        super().__init__(message)
        self.report = report


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    message: str
    elapsed_s: float = 0.0


@dataclass
class ValidationReport:
    """Aggregate result of all post-seeding validation checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True only if every check passed."""
        return all(c.passed for c in self.checks)

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


class SeedingValidator:
    """Runs post-seeding health checks against the database."""

    async def validate(self, session: Any) -> ValidationReport:
        """Execute all checks and return a ValidationReport.

        Args:
            session: SQLAlchemy AsyncSession.

        Returns:
            ValidationReport with per-check results.

        Raises:
            SeedingValidationError: if any check fails.
        """
        report = ValidationReport()

        report.checks.append(await self._check_geo_event_count(session))
        report.checks.append(await self._check_embedding_count_matches(session))
        report.checks.append(await self._check_cosine_query_latency(session))
        report.checks.append(await self._check_price_exposure_count(session))

        if not report.passed:
            failed = ", ".join(c.name for c in report.failed_checks())
            raise SeedingValidationError(
                f"Seeding validation failed on checks: {failed}",
                report=report,
            )

        logger.info(
            "SeedingValidator: all %d checks passed.", len(report.checks)
        )
        return report

    @staticmethod
    async def _check_geo_event_count(session: Any) -> CheckResult:
        """Check: at least one geo_event row from gdelt or acled."""
        name = "geo_event_count"
        start = time.monotonic()
        try:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM geo_event "
                    "WHERE source_provider IN ('gdelt', 'acled')"
                )
            )
            count = result.scalar() or 0
            elapsed = time.monotonic() - start
            if count > 0:
                return CheckResult(
                    name=name,
                    passed=True,
                    message=f"geo_event count: {count}",
                    elapsed_s=elapsed,
                )
            else:
                return CheckResult(
                    name=name,
                    passed=False,
                    message="No geo_event rows found from gdelt or acled providers",
                    elapsed_s=elapsed,
                )
        except Exception as exc:
            return CheckResult(
                name=name,
                passed=False,
                message=f"Query failed: {exc}",
                elapsed_s=time.monotonic() - start,
            )

    @staticmethod
    async def _check_embedding_count_matches(session: Any) -> CheckResult:
        """Check: event_embedding count equals geo_event count."""
        name = "embedding_count_matches"
        start = time.monotonic()
        try:
            geo_result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM geo_event "
                    "WHERE source_provider IN ('gdelt', 'acled')"
                )
            )
            geo_count = geo_result.scalar() or 0

            emb_result = await session.execute(
                text("SELECT COUNT(*) FROM event_embedding")
            )
            emb_count = emb_result.scalar() or 0

            elapsed = time.monotonic() - start
            if emb_count == geo_count:
                return CheckResult(
                    name=name,
                    passed=True,
                    message=f"event_embedding count ({emb_count}) == geo_event count ({geo_count})",
                    elapsed_s=elapsed,
                )
            else:
                return CheckResult(
                    name=name,
                    passed=False,
                    message=(
                        f"Mismatch: event_embedding={emb_count}, "
                        f"geo_event={geo_count}"
                    ),
                    elapsed_s=elapsed,
                )
        except Exception as exc:
            return CheckResult(
                name=name,
                passed=False,
                message=f"Query failed: {exc}",
                elapsed_s=time.monotonic() - start,
            )

    @staticmethod
    async def _check_cosine_query_latency(session: Any) -> CheckResult:
        """Check: pgvector cosine query returns in under 2 seconds."""
        name = "cosine_query_latency"
        start = time.monotonic()
        # VECTOR(1536) zero vector for a test query
        zero_vector = "[" + ",".join(["0"] * 1536) + "]"
        try:
            await session.execute(
                text(
                    f"SELECT event_id FROM event_embedding "
                    f"ORDER BY embedding <=> '{zero_vector}'::vector "
                    f"LIMIT 1"
                )
            )
            elapsed = time.monotonic() - start
            if elapsed < COSINE_QUERY_TIMEOUT_S:
                return CheckResult(
                    name=name,
                    passed=True,
                    message=f"Cosine query completed in {elapsed:.3f}s",
                    elapsed_s=elapsed,
                )
            else:
                return CheckResult(
                    name=name,
                    passed=False,
                    message=(
                        f"Cosine query too slow: {elapsed:.3f}s "
                        f"(threshold: {COSINE_QUERY_TIMEOUT_S}s)"
                    ),
                    elapsed_s=elapsed,
                )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return CheckResult(
                name=name,
                passed=False,
                message=f"Query failed: {exc}",
                elapsed_s=elapsed,
            )

    @staticmethod
    async def _check_price_exposure_count(session: Any) -> CheckResult:
        """Check: at least one event_exposure row has price_change_t1d populated."""
        name = "price_exposure_count"
        start = time.monotonic()
        try:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM event_exposure "
                    "WHERE price_change_t1d IS NOT NULL"
                )
            )
            count = result.scalar() or 0
            elapsed = time.monotonic() - start
            if count > 0:
                return CheckResult(
                    name=name,
                    passed=True,
                    message=f"event_exposure rows with price_change_t1d: {count}",
                    elapsed_s=elapsed,
                )
            else:
                return CheckResult(
                    name=name,
                    passed=False,
                    message="No event_exposure rows with price_change_t1d; run PriceSeeder first",
                    elapsed_s=elapsed,
                )
        except Exception as exc:
            return CheckResult(
                name=name,
                passed=False,
                message=f"Query failed: {exc}",
                elapsed_s=time.monotonic() - start,
            )
