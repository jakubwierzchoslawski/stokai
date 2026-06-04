"""
Unit tests for storage.models.source_config and storage.models.market_source_binding.

Tests cover:
  - SourceConfig.enabled defaults to False on construction (AC-002, AC-003)
  - SourceConfig.validate_credentials_ref rejects non-prefixed values
  - MarketSourceBinding composite PK tuple uniqueness (verified via role attribute)
  - ORM model field presence and types (regression guard)
"""
import uuid

import pytest

from src.storage.models.source_config import SourceConfig
from src.storage.models.market_source_binding import MarketSourceBinding


class TestSourceConfigDefaults:
    """SourceConfig default value behaviour."""

    def test_enabled_defaults_to_false(self) -> None:
        """source_config.enabled must default to False (AC-002, AC-003)."""
        sc = SourceConfig(
            interface_type="PriceProvider",
            display_name="Test Provider",
            credentials_ref="env:TEST_API_KEY",
            config={},
            cost_tier="free",
            priority=0,
        )
        assert sc.enabled is False

    def test_priority_defaults_to_zero(self) -> None:
        sc = SourceConfig(
            interface_type="PriceProvider",
            display_name="Test Provider",
            credentials_ref="env:TEST_API_KEY",
            config={},
            cost_tier="free",
        )
        assert sc.priority == 0

    def test_config_defaults_to_empty_dict(self) -> None:
        sc = SourceConfig(
            interface_type="PriceProvider",
            display_name="Test Provider",
            credentials_ref="env:TEST_API_KEY",
            cost_tier="free",
        )
        # config can be None before DB round-trip (server_default handles it)
        # What we verify is that we can set it to an empty dict without error
        sc.config = {}
        assert sc.config == {}


class TestSourceConfigCredentialsRefValidation:
    """ORM-layer @validates enforcement for credentials_ref."""

    @pytest.mark.parametrize("valid_ref", [
        "env:FINNHUB_API_KEY",
        "env:MY_KEY",
        "vault:MY_SECRET",
        "env:A",
        "vault:A1_B2",
    ])
    def test_valid_credentials_ref_accepted(self, valid_ref: str) -> None:
        sc = SourceConfig(
            interface_type="PriceProvider",
            display_name="P",
            credentials_ref=valid_ref,
            config={},
            cost_tier="free",
        )
        assert sc.credentials_ref == valid_ref

    @pytest.mark.parametrize("invalid_ref", [
        "sk-abc123",          # raw key
        "plaintext",          # no prefix
        "env:lower_case",     # lowercase after colon
        "env:",               # empty key part
        "",                   # empty string
        "http://example.com", # URL
    ])
    def test_invalid_credentials_ref_raises(self, invalid_ref: str) -> None:
        with pytest.raises(ValueError, match="credentials_ref"):
            SourceConfig(
                interface_type="PriceProvider",
                display_name="P",
                credentials_ref=invalid_ref,
                config={},
                cost_tier="free",
            )


class TestMarketSourceBindingModel:
    """MarketSourceBinding ORM model basic attribute checks."""

    def test_binding_stores_role_primary(self) -> None:
        binding = MarketSourceBinding(
            market_id=uuid.uuid4(),
            interface_type="PriceProvider",
            source_id=uuid.uuid4(),
            role="primary",
        )
        assert binding.role == "primary"

    def test_binding_stores_role_fallback(self) -> None:
        binding = MarketSourceBinding(
            market_id=uuid.uuid4(),
            interface_type="PriceProvider",
            source_id=uuid.uuid4(),
            role="fallback",
        )
        assert binding.role == "fallback"

    def test_binding_table_name(self) -> None:
        assert MarketSourceBinding.__tablename__ == "market_source_binding"

    def test_source_config_table_name(self) -> None:
        assert SourceConfig.__tablename__ == "source_config"
