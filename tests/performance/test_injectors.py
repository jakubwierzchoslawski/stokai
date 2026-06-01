"""TDD tests for EventInjector Protocol and concrete injectors.

Tests written FIRST (TDD red phase) before the implementations are written.
These tests verify the injector contracts specified in PLAN-N-001 TASK-001.

Tests:
    test_tweet_injector_produces_distinct_payloads
    test_gdelt_injector_source_type
    test_edgar_injector_filing_timestamp_present
    test_conftest_db_session_fixture_connects (see conftest.py)
    test_lm_mock_returns_in_under_5ms (see test_conftest_fixtures.py)
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime


class TestTweetInjectorDistinctPayloads:
    """Verifies TweetEventInjector produces distinct payloads per index.

    PLAN-N-001 TASK-001 AC: each build_payload(index) call must produce a
    payload with unique content to prevent deduplication from collapsing the
    100-event test run.
    """

    def test_tweet_injector_produces_distinct_payloads(self) -> None:
        """Call build_payload 10 times; assert all raw_payload dicts are distinct."""
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        payloads = [injector.build_payload(i).raw_payload for i in range(10)]

        # Serialize to frozenset of items for comparison; each must be unique
        serialized = [str(p) for p in payloads]
        assert len(set(serialized)) == 10, (
            f"Expected 10 distinct payloads but got {len(set(serialized))} unique: "
            f"{serialized}"
        )

    def test_tweet_injector_source_type(self) -> None:
        """TweetEventInjector.source_type must be 'X_FILTERED_STREAM'."""
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        assert injector.source_type == "X_FILTERED_STREAM"

    def test_tweet_injector_payload_has_required_fields(self) -> None:
        """Each tweet payload must have text, user, and timestamp fields."""
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        payload = injector.build_payload(0)

        assert "text" in payload.raw_payload
        assert "user" in payload.raw_payload
        assert "timestamp" in payload.raw_payload

    def test_tweet_injector_detected_at_is_set(self) -> None:
        """Each payload must have detected_at set at construction time."""
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        before = datetime.utcnow()
        payload = injector.build_payload(0)
        after = datetime.utcnow()

        assert before <= payload.detected_at <= after


class TestGdeltInjector:
    """Verifies GdeltEventInjector contracts."""

    def test_gdelt_injector_source_type(self) -> None:
        """GdeltEventInjector.source_type must equal 'GDELT'."""
        from tests.performance.injectors.gdelt_injector import GdeltEventInjector

        injector = GdeltEventInjector()
        assert injector.source_type == "GDELT"

    def test_gdelt_injector_payload_has_geo_fields(self) -> None:
        """GDELT payloads must include lat, lon, and category fields."""
        from tests.performance.injectors.gdelt_injector import GdeltEventInjector

        injector = GdeltEventInjector()
        payload = injector.build_payload(0)

        assert "lat" in payload.raw_payload
        assert "lon" in payload.raw_payload
        assert "category" in payload.raw_payload

    def test_gdelt_injector_produces_distinct_payloads(self) -> None:
        """Each build_payload(index) call must produce a distinct payload."""
        from tests.performance.injectors.gdelt_injector import GdeltEventInjector

        injector = GdeltEventInjector()
        payloads = [str(injector.build_payload(i).raw_payload) for i in range(10)]
        assert len(set(payloads)) == 10


class TestEdgarInjector:
    """Verifies EdgarEventInjector contracts."""

    def test_edgar_injector_source_type(self) -> None:
        """EdgarEventInjector.source_type must equal 'SEC_EDGAR'."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector

        injector = EdgarEventInjector()
        assert injector.source_type == "SEC_EDGAR"

    def test_edgar_injector_filing_timestamp_present(self) -> None:
        """filing_timestamp key must be present in each built payload's raw_payload."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector

        injector = EdgarEventInjector()
        for i in range(5):
            payload = injector.build_payload(i)
            assert "filing_timestamp" in payload.raw_payload, (
                f"filing_timestamp missing in payload index {i}: {payload.raw_payload}"
            )

    def test_edgar_injector_has_unique_cik_and_accession(self) -> None:
        """Each EDGAR payload must have a unique CIK and accession number."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector

        injector = EdgarEventInjector()
        payloads = [injector.build_payload(i).raw_payload for i in range(10)]

        ciks = [p["cik"] for p in payloads]
        accessions = [p["accession_number"] for p in payloads]

        assert len(set(ciks)) == 10, "CIKs are not unique"
        assert len(set(accessions)) == 10, "Accession numbers are not unique"

    def test_edgar_injector_produces_distinct_payloads(self) -> None:
        """Each build_payload(index) call must produce a distinct payload."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector

        injector = EdgarEventInjector()
        payloads = [str(injector.build_payload(i).raw_payload) for i in range(10)]
        assert len(set(payloads)) == 10


class TestEventInjectorProtocol:
    """Verifies Protocol compliance for all injectors."""

    def test_tweet_injector_conforms_to_protocol(self) -> None:
        """TweetEventInjector must satisfy the EventInjector Protocol."""
        from tests.performance.injectors.base import EventInjector
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        # Runtime Protocol check: must have source_type and build_payload
        assert hasattr(injector, "source_type")
        assert hasattr(injector, "build_payload")
        assert callable(injector.build_payload)

    def test_gdelt_injector_conforms_to_protocol(self) -> None:
        """GdeltEventInjector must satisfy the EventInjector Protocol."""
        from tests.performance.injectors.gdelt_injector import GdeltEventInjector

        injector = GdeltEventInjector()
        assert hasattr(injector, "source_type")
        assert hasattr(injector, "build_payload")
        assert callable(injector.build_payload)

    def test_edgar_injector_conforms_to_protocol(self) -> None:
        """EdgarEventInjector must satisfy the EventInjector Protocol."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector

        injector = EdgarEventInjector()
        assert hasattr(injector, "source_type")
        assert hasattr(injector, "build_payload")
        assert callable(injector.build_payload)

    def test_build_payload_returns_raw_event_payload(self) -> None:
        """build_payload must return a RawEventPayload instance."""
        from src.event_pipeline.pipeline_state import RawEventPayload
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        injector = TweetEventInjector()
        payload = injector.build_payload(0)
        assert isinstance(payload, RawEventPayload)

    def test_all_payloads_have_tenant_id(self) -> None:
        """All injectors must set a non-null tenant_id on their payloads."""
        from tests.performance.injectors.edgar_injector import EdgarEventInjector
        from tests.performance.injectors.gdelt_injector import GdeltEventInjector
        from tests.performance.injectors.tweet_injector import TweetEventInjector

        for InjectorClass in [TweetEventInjector, GdeltEventInjector, EdgarEventInjector]:
            injector = InjectorClass()
            payload = injector.build_payload(0)
            assert payload.tenant_id is not None
            assert isinstance(payload.tenant_id, uuid.UUID)
