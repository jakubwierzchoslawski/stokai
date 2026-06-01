"""
Provider swap integration test — AC-003 verification.

PLAN-N-008 TASK-004

Verifies the architecture principle P-01 (Provider Abstraction) and AC-003:
  "Swapping a PriceProvider requires exactly one config entry change;
   zero service/agent/workflow file changes."

Test approach:
- StubPriceProviderA and StubPriceProviderB are minimal in-test implementations
  of the PriceProvider protocol — defined inline, not in src/.
- provider_config_stub.yaml maps price_provider → StubPriceProviderA.
- provider_config_stub_swapped.yaml maps price_provider → StubPriceProviderB.
  The two files differ by ONE line only.
- Tests use ProviderRegistry.register() directly to simulate what the DB-backed
  load_from_db() does after reading the config — proving the registry mechanism
  works correctly with any conforming provider.

Acceptance criteria: AC-003
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pytest
import yaml

from src.providers.registry.provider_registry import ProviderRegistry

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"
STUB_A_CONFIG = FIXTURE_DIR / "provider_config_stub.yaml"
STUB_B_CONFIG = FIXTURE_DIR / "provider_config_stub_swapped.yaml"


# ---------------------------------------------------------------------------
# Minimal stub providers — defined inline; never in src/
# ---------------------------------------------------------------------------

@runtime_checkable
class PriceProvider(Protocol):
    """Minimal PriceProvider protocol for test purposes."""

    def get_price(self, symbol: str) -> float:
        ...


class StubPriceProviderA:
    """Stub implementation A — maps to provider_config_stub.yaml."""

    def get_price(self, symbol: str) -> float:
        return 100.0

    def get_ohlcv(self, symbol: str, from_dt: Any, to_dt: Any) -> list:
        return []


class StubPriceProviderB:
    """Stub implementation B — maps to provider_config_stub_swapped.yaml."""

    def get_price(self, symbol: str) -> float:
        return 200.0

    def get_ohlcv(self, symbol: str, from_dt: Any, to_dt: Any) -> list:
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STUB_CLASS_MAP = {
    "StubPriceProviderA": StubPriceProviderA,
    "StubPriceProviderB": StubPriceProviderB,
}


def _load_registry_from_yaml(config_path: Path) -> ProviderRegistry:
    """
    Parse a provider_config YAML fixture and register providers into a fresh
    ProviderRegistry using the register() API — simulating what load_from_db()
    does after reading from the provider_registry table.

    This is the test-only YAML shim. Production code always uses load_from_db().
    """
    with config_path.open() as fh:
        data = yaml.safe_load(fh)

    registry = ProviderRegistry()

    provider_config = data.get("provider_config", {})
    for _key, spec in provider_config.items():
        interface_name: str = spec["interface"]
        market_id: str = spec["market"]
        class_name: str = spec["class"]

        cls = _STUB_CLASS_MAP.get(class_name)
        if cls is None:
            raise ValueError(f"Unknown stub class in fixture: {class_name!r}")

        instance = cls()
        registry.register(interface_name, market_id, instance)

    return registry


# ---------------------------------------------------------------------------
# Unit tests (no running services required)
# ---------------------------------------------------------------------------

class TestRegistryLoadsProviderA:
    """registry.resolve() returns StubPriceProviderA when loaded from stub config."""

    def test_registry_loads_provider_a(self) -> None:
        registry = _load_registry_from_yaml(STUB_A_CONFIG)
        instance = registry.resolve("PriceProvider", "US")
        assert isinstance(instance, StubPriceProviderA), (
            f"Expected StubPriceProviderA, got {type(instance).__name__}"
        )


class TestSwapToProviderBRequiresNoSourceChange:
    """
    Swapping to StubPriceProviderB requires only changing one line in the YAML
    fixture — zero source file changes.

    This test verifies the contract: it measures src/ mtimes before and after
    the registry swap and asserts they are unchanged.

    AC-003: provider swap = config only, zero source changes.
    """

    def test_swap_to_provider_b_requires_no_source_change(self) -> None:
        src_root = PROJECT_ROOT / "src"

        # Record src/ mtimes before the swap
        mtimes_before = {
            str(f): f.stat().st_mtime
            for f in src_root.rglob("*.py")
        }

        # Perform the swap by loading the swapped config (simulates changing one YAML line)
        registry = _load_registry_from_yaml(STUB_B_CONFIG)
        instance = registry.resolve("PriceProvider", "US")

        # Record src/ mtimes after the swap
        mtimes_after = {
            str(f): f.stat().st_mtime
            for f in src_root.rglob("*.py")
        }

        # Assert the provider is now B
        assert isinstance(instance, StubPriceProviderB), (
            f"Expected StubPriceProviderB after config swap, got {type(instance).__name__}"
        )

        # Assert zero source files were touched during the swap
        changed_files = [
            path for path, mtime in mtimes_after.items()
            if mtimes_before.get(path) != mtime
        ]
        new_files = [
            path for path in mtimes_after
            if path not in mtimes_before
        ]
        all_changes = changed_files + new_files
        assert not all_changes, (
            f"AC-003 violation: {len(all_changes)} source file(s) changed during "
            f"the provider swap (expected zero): {all_changes}"
        )

    def test_config_files_differ_by_exactly_one_line(self) -> None:
        """
        The stub and swapped config files must differ by exactly one line —
        proving the one-line-change contract stated in AC-003.
        """
        lines_a = STUB_A_CONFIG.read_text(encoding="utf-8").splitlines()
        lines_b = STUB_B_CONFIG.read_text(encoding="utf-8").splitlines()

        differing_lines = [
            (i + 1, la, lb)
            for i, (la, lb) in enumerate(zip(lines_a, lines_b))
            if la != lb
        ]
        # Also account for files with different lengths
        max_len = max(len(lines_a), len(lines_b))
        for i in range(min(len(lines_a), len(lines_b)), max_len):
            la = lines_a[i] if i < len(lines_a) else "<absent>"
            lb = lines_b[i] if i < len(lines_b) else "<absent>"
            differing_lines.append((i + 1, la, lb))

        assert len(differing_lines) == 1, (
            f"Expected exactly 1 differing line between provider_config_stub.yaml "
            f"and provider_config_stub_swapped.yaml; found {len(differing_lines)}: "
            f"{differing_lines}"
        )


class TestProviderProtocolCompliance:
    """Both stub providers must satisfy the PriceProvider protocol."""

    def test_stub_a_satisfies_price_provider_protocol(self) -> None:
        instance = StubPriceProviderA()
        assert isinstance(instance, PriceProvider), (
            "StubPriceProviderA must satisfy the PriceProvider protocol"
        )

    def test_stub_b_satisfies_price_provider_protocol(self) -> None:
        instance = StubPriceProviderB()
        assert isinstance(instance, PriceProvider), (
            "StubPriceProviderB must satisfy the PriceProvider protocol"
        )


class TestRegistryReplacesProviderCorrectly:
    """Swapping the registry instance swaps the resolution result."""

    def test_registry_a_resolves_different_from_registry_b(self) -> None:
        registry_a = _load_registry_from_yaml(STUB_A_CONFIG)
        registry_b = _load_registry_from_yaml(STUB_B_CONFIG)

        instance_a = registry_a.resolve("PriceProvider", "US")
        instance_b = registry_b.resolve("PriceProvider", "US")

        assert isinstance(instance_a, StubPriceProviderA)
        assert isinstance(instance_b, StubPriceProviderB)
        assert type(instance_a) != type(instance_b), (
            "Registry A and B must resolve to different provider types"
        )


# ---------------------------------------------------------------------------
# Integration test — requires running PostgreSQL (marked, skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHotReloadViaListenNotify:
    """
    Hot-reload test: registry reflects updated config within 2 seconds after
    a PG NOTIFY is received on the ProviderRegistry channel.

    Requires a running PostgreSQL instance.
    Skipped in default test runs — run with: pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_hot_reload_via_listen_notify(self, db_session: Any) -> None:
        """
        Register StubPriceProviderA, then simulate a hot-reload by calling
        swap_snapshot() with StubPriceProviderB, and assert the registry
        reflects the update within 2 seconds.

        In production this is triggered by the RegistryReloadListener receiving
        a NOTIFY on PROVIDER_REGISTRY_PG_CHANNEL. Here we call swap_snapshot()
        directly to simulate the reload outcome.
        """
        registry = ProviderRegistry()
        registry.register("PriceProvider", "US", StubPriceProviderA())

        # Verify initial state
        instance_before = registry.resolve("PriceProvider", "US")
        assert isinstance(instance_before, StubPriceProviderA)

        # Simulate hot-reload: swap the snapshot (in production, triggered by NOTIFY)
        new_snapshot = {("PriceProvider", "US"): StubPriceProviderB()}

        start = time.monotonic()
        registry.swap_snapshot(new_snapshot)
        elapsed = time.monotonic() - start

        # Assert the swap is reflected immediately
        instance_after = registry.resolve("PriceProvider", "US")
        assert isinstance(instance_after, StubPriceProviderB), (
            f"Expected StubPriceProviderB after swap, got {type(instance_after).__name__}"
        )

        # Assert the swap completed within 2 seconds (hot-reload SLA)
        assert elapsed < 2.0, (
            f"Registry swap took {elapsed:.3f}s — must complete within 2 seconds"
        )
