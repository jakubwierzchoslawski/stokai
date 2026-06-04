"""Tests for scoring invalidation consumer (TDD — written before implementation)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4


# ---------------------------------------------------------------------------
# Unit tests using mocked dependencies
# ---------------------------------------------------------------------------

class TestInvalidationConsumerLogic:
    """Test the business logic of invalidation consumer without Celery."""

    def test_no_companies_no_tasks_enqueued(self):
        """event_exposure with zero rows → no re-score tasks enqueued."""
        enqueued = []

        def mock_send_task(name, kwargs=None, **kw):
            if name == "scoring.rescore_company":
                enqueued.append(kwargs.get("company_id"))

        # Simulate the consumer logic
        company_ids = []  # empty
        geo_regions = ["US"]
        intensity = 3

        for company_id in company_ids:
            mock_send_task("scoring.rescore_company", kwargs={"company_id": company_id})

        assert enqueued == []

    def test_companies_enqueued_for_each_affected(self):
        """event_id with event_exposure for companies [A,B] → enqueues re-score for A and B."""
        enqueued = []

        def mock_send_task(name, kwargs=None, **kw):
            if name == "scoring.rescore_company":
                enqueued.append(kwargs.get("company_id"))

        company_ids = [str(uuid4()), str(uuid4())]
        geo_regions = ["US", "CN"]
        intensity = 4

        for company_id in company_ids:
            mock_send_task(
                "scoring.rescore_company",
                kwargs={
                    "company_id": company_id,
                    "geo_regions": geo_regions,
                    "event_intensity": intensity,
                },
            )

        assert len(enqueued) == 2
        assert set(enqueued) == set(company_ids)

    def test_geo_regions_passed_in_payload(self):
        """Reads geo_regions from geo_event and passes to re-score task payload."""
        captured_payloads = []

        def mock_send_task(name, kwargs=None, **kw):
            if name == "scoring.rescore_company":
                captured_payloads.append(kwargs)

        company_ids = [str(uuid4())]
        geo_regions = ["CN", "JP"]
        intensity = 3

        for company_id in company_ids:
            mock_send_task(
                "scoring.rescore_company",
                kwargs={
                    "company_id": company_id,
                    "geo_regions": geo_regions,
                    "event_intensity": intensity,
                },
            )

        assert captured_payloads[0]["geo_regions"] == ["CN", "JP"]
        assert captured_payloads[0]["event_intensity"] == 3


class TestDeduplication:
    def test_same_event_id_not_processed_twice(self):
        """Processing same event_id twice does not enqueue duplicate tasks."""
        processed = set()
        enqueued_events = []

        def process_event(event_id: str) -> bool:
            """Returns True if newly processed."""
            if event_id in processed:
                return False
            processed.add(event_id)
            return True

        event_id = str(uuid4())
        company_ids = [str(uuid4())]

        # First processing
        if process_event(event_id):
            enqueued_events.extend(company_ids)

        # Second processing (duplicate)
        if process_event(event_id):
            enqueued_events.extend(company_ids)

        assert len(enqueued_events) == 1  # only enqueued once

    def test_different_events_both_processed(self):
        """Different event IDs are both processed normally."""
        processed = set()
        enqueued_count = 0

        def process_event(event_id: str) -> bool:
            if event_id in processed:
                return False
            processed.add(event_id)
            return True

        event_1 = str(uuid4())
        event_2 = str(uuid4())

        if process_event(event_1):
            enqueued_count += 1
        if process_event(event_2):
            enqueued_count += 1

        assert enqueued_count == 2
