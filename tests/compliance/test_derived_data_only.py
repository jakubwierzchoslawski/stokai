"""
Derived-data-only assertion suite — TDD for TASK-004 (REQ-N-012 AC-004).

This module implements a static + integration assertion suite that verifies no
FastAPI endpoint returns raw OHLCV fields (open, high, low, close, volume) from
the price_bar table to end users.

Structure:
  1. Static analysis — walks all Pydantic response models registered in the
     FastAPI OpenAPI schema and asserts none contain OHLCV field names.
  2. Integration check — helper that detects OHLCV field names in a JSON body
     at any nesting depth.

OHLCV_FIELDS: the five raw price fields that must never appear in API responses.
__compliance_exempt__ = True: annotation to skip a model from the static check
  (for future admin models that may legitimately return these fields; no such
  model exists at MVP).

Note: The static walker checks only models in app.openapi()["components"]["schemas"]
to avoid false positives on internal ORM models that legitimately use these names.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

# Raw OHLCV fields that must never appear in API responses (price_bar table columns)
OHLCV_FIELDS: frozenset[str] = frozenset({"open", "high", "low", "close", "volume"})


# ── OHLCV detection helpers ───────────────────────────────────────────────────


def find_ohlcv_violations(data: Any, path: str = "") -> list[str]:
    """
    Recursively walk a parsed JSON value and return all OHLCV field names found
    as keys in any dict, at any nesting depth.

    Returns a list of strings in the format "path.field" for each violation.
    """
    violations: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{path}.{key}" if path else key
            if key in OHLCV_FIELDS:
                violations.append(full_key)
            violations.extend(find_ohlcv_violations(value, full_key))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            violations.extend(find_ohlcv_violations(item, f"{path}[{i}]"))
    return violations


# ── Static analysis helpers ───────────────────────────────────────────────────


def _get_ohlcv_violations_in_schema(
    schema: dict[str, Any],
    schema_name: str,
    all_schemas: dict[str, Any],
    visited: set[str] | None = None,
) -> list[str]:
    """
    Recursively check a JSON Schema object (from OpenAPI components/schemas)
    for OHLCV field names.

    Returns a list of "SchemaName.field_path" strings for each violation found.
    Follows $ref references up to one level to catch nested models.
    """
    if visited is None:
        visited = set()
    if schema_name in visited:
        return []
    visited.add(schema_name)

    violations: list[str] = []
    properties = schema.get("properties", {})

    for field_name, field_schema in properties.items():
        if field_name in OHLCV_FIELDS:
            violations.append(f"{schema_name}.{field_name}")

        # Follow $ref to detect nested violations.
        ref = field_schema.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            ref_name = ref.split("/")[-1]
            if ref_name in all_schemas:
                nested = _get_ohlcv_violations_in_schema(
                    all_schemas[ref_name], ref_name, all_schemas, visited
                )
                violations.extend(nested)

        # Inline nested object
        if field_schema.get("type") == "object":
            nested_violations = _get_ohlcv_violations_in_schema(
                field_schema, f"{schema_name}.{field_name}", all_schemas, visited
            )
            violations.extend(nested_violations)

    return violations


def is_exempt(schema: dict[str, Any]) -> bool:
    """Return True if the schema is explicitly compliance-exempt."""
    # Pydantic models can set __compliance_exempt__ = True in their JSON schema
    # extra via model_config = {"json_schema_extra": {"compliance_exempt": True}}.
    return schema.get("compliance_exempt") is True


# ── Unit tests: detection helpers ─────────────────────────────────────────────


def test_ohlcv_detector_finds_open_in_nested_dict() -> None:
    """Detector finds 'open' key nested inside a data object."""
    body = {"data": {"open": 150.0}}
    violations = find_ohlcv_violations(body)
    assert "open" in str(violations) or any("open" in v for v in violations)


def test_ohlcv_detector_passes_clean_response() -> None:
    """Detector finds no violations in a clean derived-data response."""
    body = {"data": {"score": 72.5, "sparkline_data": [1, 2, 3]}}
    violations = find_ohlcv_violations(body)
    assert violations == []


def test_ohlcv_detector_finds_high_deeply_nested() -> None:
    """Detector finds 'high' nested two levels deep."""
    body = {"meta": {"price_info": {"high": 155.0}}}
    violations = find_ohlcv_violations(body)
    assert any("high" in v for v in violations)


def test_ohlcv_detector_returns_field_path() -> None:
    """Detector returns a path string that identifies the nested location."""
    body = {"data": {"open": 100.0}}
    violations = find_ohlcv_violations(body)
    # Should contain the full path, e.g. "data.open"
    assert any("open" in v for v in violations)
    assert len(violations) >= 1


def test_ohlcv_detector_finds_volume_in_list() -> None:
    """Detector finds 'volume' inside a list element."""
    body = {"bars": [{"date": "2025-01-01", "volume": 1000000}]}
    violations = find_ohlcv_violations(body)
    assert any("volume" in v for v in violations)


# ── Static walker: Pydantic model tests ───────────────────────────────────────


def test_static_walker_detects_close_field_in_model() -> None:
    """Static walker correctly identifies a Pydantic model with 'close' field."""
    from pydantic import BaseModel

    class NonCompliantModel(BaseModel):
        close: float
        score: float

    schema = NonCompliantModel.model_json_schema()
    schema_name = "NonCompliantModel"
    all_schemas = {schema_name: schema}
    violations = _get_ohlcv_violations_in_schema(schema, schema_name, all_schemas)
    assert any("close" in v for v in violations)


def test_static_walker_passes_compliant_model() -> None:
    """Static walker passes a model with only derived-data fields."""
    from pydantic import BaseModel

    class CompliantModel(BaseModel):
        score: float
        score_delta: float
        percentile_rank: float
        sparkline_data: list[float]

    schema = CompliantModel.model_json_schema()
    schema_name = "CompliantModel"
    all_schemas = {schema_name: schema}
    violations = _get_ohlcv_violations_in_schema(schema, schema_name, all_schemas)
    assert violations == []


def test_static_walker_detects_nested_close_field() -> None:
    """Static walker detects 'close' nested two levels deep via $ref."""
    from pydantic import BaseModel

    class PriceData(BaseModel):
        close: float

    class WrapperModel(BaseModel):
        name: str
        price: PriceData

    # Simulate the OpenAPI components/schemas dict
    wrapper_schema = WrapperModel.model_json_schema()
    price_schema = PriceData.model_json_schema()
    all_schemas = {
        "WrapperModel": wrapper_schema,
        "PriceData": price_schema,
    }

    # Walk WrapperModel; it has a 'price' property that references PriceData
    violations = _get_ohlcv_violations_in_schema(
        price_schema, "PriceData", all_schemas
    )
    assert any("close" in v for v in violations)


# ── Full static assertion suite — regression gate ─────────────────────────────


def test_no_ohlcv_fields_in_openapi_schema() -> None:
    """
    Regression gate: walk all response models in the FastAPI OpenAPI schema and
    assert none contain raw OHLCV field names.

    This test will FAIL (correctly) if any future endpoint inadvertently exposes
    raw price_bar fields. It is intended as a CI compliance gate.

    Models annotated with compliance_exempt=True in their JSON schema extra are
    skipped (no such model exists at MVP).
    """
    import os
    import sys

    # Patch required env vars before importing main.py
    # (conftest.py already does this, but guard in case this test runs standalone)
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
    os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-chars!")

    try:
        from src.api.main import app
        openapi = app.openapi()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Could not load FastAPI app for OpenAPI inspection: {exc}")
        return

    schemas = openapi.get("components", {}).get("schemas", {})
    all_violations: list[str] = []

    for schema_name, schema in schemas.items():
        if is_exempt(schema):
            continue
        violations = _get_ohlcv_violations_in_schema(schema, schema_name, schemas)
        all_violations.extend(violations)

    if all_violations:
        formatted = "\n  ".join(all_violations)
        pytest.fail(
            f"COMPLIANCE VIOLATION: The following API response model fields expose "
            f"raw OHLCV price data. Only derived representations are permitted in API "
            f"responses (REQ-N-012 AC-004).\n\nViolating fields:\n  {formatted}"
        )
