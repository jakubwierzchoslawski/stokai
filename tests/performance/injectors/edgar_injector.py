"""EdgarEventInjector — builds SEC_EDGAR filing payloads for performance tests.

PLAN-N-001 TASK-001.

Each call to build_payload(index) produces a distinct EDGAR payload with
a unique CIK and accession number to prevent deduplication from collapsing
the test run.  filing_timestamp is set to datetime.utcnow() at construction.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

# Stable test tenant ID (shared across all performance injectors).
_PERF_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# SEC form types used in performance tests.
_FORM_TYPES = ["8-K", "10-K", "10-Q", "S-1", "DEF 14A", "4"]

# Realistic-sounding company names for EDGAR filings.
_COMPANY_NAMES = [
    "Alpha Holdings Corp",
    "Beta Financial Group",
    "Gamma Technologies Inc",
    "Delta Energy Partners",
    "Epsilon Healthcare Ltd",
    "Zeta Manufacturing Co",
    "Eta Capital Management",
    "Theta Retail Group",
    "Iota Logistics Corp",
    "Kappa Pharmaceuticals",
]


class EdgarEventInjector:
    """Builds SEC_EDGAR ``RawEventPayload`` instances for latency tests.

    Implements the ``EventInjector`` Protocol.

    Each ``build_payload(index)`` call generates a unique CIK (simulated as
    a padded integer) and accession number to guarantee deduplication-safe
    payloads across the 20-event EDGAR test run.

    SRP: single responsibility — builds SEC EDGAR filing payloads only.
    """

    source_type: str = "SEC_EDGAR"

    def build_payload(self, index: int) -> RawEventPayload:
        """Build a distinct SEC_EDGAR payload for the given run index.

        Parameters
        ----------
        index:
            Zero-based run counter.  CIK and accession number are derived from
            the index to guarantee uniqueness; filing_timestamp is set to
            datetime.utcnow() at call time.

        Returns
        -------
        RawEventPayload:
            Fully-populated EDGAR payload with detected_at = filing_timestamp.
        """
        now = datetime.utcnow()
        # Simulate realistic CIK (SEC uses 10-digit padded integers).
        cik = f"{1000000 + (index * 7919):010d}"  # 7919 is prime to spread CIKs
        # Accession numbers: XXXXXXXXXX-YY-ZZZZZZ format.
        year = now.year % 100
        accession_seq = index * 100 + 1
        accession_number = f"{cik[:10]}-{year:02d}-{accession_seq:06d}"

        company_name = _COMPANY_NAMES[index % len(_COMPANY_NAMES)]
        form_type = _FORM_TYPES[index % len(_FORM_TYPES)]

        raw_payload = {
            "cik": cik,
            "accession_number": accession_number,
            "company_name": company_name,
            "form_type": form_type,
            "filing_timestamp": now.isoformat(),
            "filing_date": now.strftime("%Y-%m-%d"),
            "description": (
                f"Performance test filing #{index} — {form_type} for {company_name}. "
                f"Accession: {accession_number}"
            ),
            "items": [f"Item {i + 1}.01" for i in range(index % 3 + 1)],
            "run_index": index,
        }

        return RawEventPayload(
            source=RawEventSource.SEC_EDGAR,
            raw_payload=raw_payload,
            detected_at=now,
            tenant_id=_PERF_TENANT_ID,
        )
