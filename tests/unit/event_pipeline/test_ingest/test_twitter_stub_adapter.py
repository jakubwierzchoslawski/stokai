"""Unit tests for TwitterStubAdapter and AdapterRegistry (TASK-003, TDD).

Tests written before implementation.
Covers: AC-001, C-002 (Twitter/X toggle).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTwitterStubRaisesProviderDisabled:
    """test_twitter_stub_raises_provider_disabled"""

    def test_twitter_stub_raises_provider_disabled(self):
        """TwitterStubAdapter.poll() always raises ProviderDisabled."""
        from src.event_pipeline.ingest.twitter_stub_adapter import TwitterStubAdapter
        from src.event_pipeline.ingest.exceptions import ProviderDisabled

        tenant_id = uuid.uuid4()
        adapter = TwitterStubAdapter(tenant_id=tenant_id)

        with pytest.raises(ProviderDisabled):
            adapter.poll()


class TestAdapterRegistrySkipsDisabledSource:
    """test_adapter_registry_skips_disabled_source"""

    def test_adapter_registry_skips_disabled_source(self):
        """AdapterRegistry.is_enabled returns False for X_FILTERED_STREAM when TWITTER_ENABLED=false."""
        from src.event_pipeline.ingest.adapter_registry import AdapterRegistry
        from src.event_pipeline.pipeline_state import RawEventSource

        with patch.dict("os.environ", {"TWITTER_ENABLED": "false"}):
            registry = AdapterRegistry(tenant_id=uuid.uuid4())
            assert registry.is_enabled(RawEventSource.X_FILTERED_STREAM) is False

    def test_adapter_registry_gdelt_always_enabled(self):
        """AdapterRegistry.is_enabled returns True for GDELT by default."""
        from src.event_pipeline.ingest.adapter_registry import AdapterRegistry
        from src.event_pipeline.pipeline_state import RawEventSource

        registry = AdapterRegistry(tenant_id=uuid.uuid4())
        assert registry.is_enabled(RawEventSource.GDELT) is True
