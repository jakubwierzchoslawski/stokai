"""Indicator service — CRUD, versioning, DSL diff, and rollback.

Pure business logic. Wraps IIndicatorRepository and DslValidator.
No DB access except through injected repository.
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.scoring.dsl.tokenizer import tokenize
from src.scoring.dsl.validator import DslValidator, ValidationResult
from src.scoring.repositories.interfaces import IIndicatorRepository
from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord

logger = logging.getLogger(__name__)


class DslValidationError(Exception):
    """Raised when DSL formula fails semantic validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"DSL validation failed: {errors}")


@dataclass(frozen=True)
class DiffResult:
    """Token-level diff between two DSL versions."""
    added_tokens: list[str]
    removed_tokens: list[str]
    unchanged_tokens: list[str]


class IndicatorService:
    """Business logic for indicator management.

    Constructor parameters are injected — no direct DB/external-API access.
    """

    def __init__(
        self,
        repository: IIndicatorRepository,
        validator: DslValidator,
    ) -> None:
        self._repo = repository
        self._validator = validator

    async def create_indicator(
        self,
        tenant_id: UUID,
        name: str,
        formula_dsl: str,
        normalization_mode: str = "percentile",
        normalization_config: dict | None = None,
        direction: str = "higher_better",
        geo_weight: float = 0.0,
    ) -> IndicatorRecord:
        """Create a new indicator with version=1.

        Raises:
            DslValidationError: if the DSL formula fails validation.
        """
        await self._validate_dsl(formula_dsl, tenant_id)

        record = IndicatorRecord.new(
            tenant_id=tenant_id,
            name=name,
            formula_dsl=formula_dsl,
            normalization_mode=normalization_mode,
            normalization_config=normalization_config or {},
            direction=direction,
            geo_weight=geo_weight,
        )
        return await self._repo.save(record)

    async def update_indicator(
        self,
        indicator_id: UUID,
        tenant_id: UUID,
        *,
        formula_dsl: str | None = None,
        name: str | None = None,
        normalization_mode: str | None = None,
        normalization_config: dict | None = None,
        direction: str | None = None,
        geo_weight: float | None = None,
    ) -> IndicatorRecord:
        """Update an indicator, creating a new version.

        Raises:
            ValueError: if indicator not found.
            DslValidationError: if new DSL formula is invalid.
        """
        existing = await self._repo.get_by_id(indicator_id, tenant_id)
        if existing is None:
            raise ValueError(f"Indicator {indicator_id} not found for tenant {tenant_id}")

        # Validate new DSL if provided
        new_dsl = formula_dsl if formula_dsl is not None else existing.formula_dsl
        if formula_dsl is not None:
            await self._validate_dsl(new_dsl, tenant_id)

        # Apply updates
        existing.formula_dsl = new_dsl
        if name is not None:
            existing.name = name
        if normalization_mode is not None:
            existing.normalization_mode = normalization_mode
        if normalization_config is not None:
            existing.normalization_config = normalization_config
        if direction is not None:
            existing.direction = direction
        if geo_weight is not None:
            existing.geo_weight = geo_weight
        existing.updated_at = datetime.utcnow()

        return await self._repo.save(existing)

    async def get_indicator(
        self, indicator_id: UUID, tenant_id: UUID
    ) -> IndicatorRecord | None:
        return await self._repo.get_by_id(indicator_id, tenant_id)

    async def list_indicators(self, tenant_id: UUID) -> list[IndicatorRecord]:
        return await self._repo.list_by_tenant(tenant_id)

    async def list_versions(
        self, indicator_id: UUID
    ) -> list[IndicatorVersionRecord]:
        return await self._repo.list_versions(indicator_id)

    async def get_diff(
        self,
        indicator_id: UUID,
        v1: int,
        v2: int,
    ) -> DiffResult:
        """Compute token-level diff between two indicator versions.

        Args:
            indicator_id: the indicator.
            v1: source version number.
            v2: target version number.

        Returns:
            DiffResult with added, removed, and unchanged token lists.

        Raises:
            ValueError: if either version does not exist.
        """
        version1 = await self._repo.get_version(indicator_id, v1)
        version2 = await self._repo.get_version(indicator_id, v2)

        if version1 is None:
            raise ValueError(f"Version {v1} not found for indicator {indicator_id}")
        if version2 is None:
            raise ValueError(f"Version {v2} not found for indicator {indicator_id}")

        return self._compute_diff(version1.formula_dsl, version2.formula_dsl)

    async def rollback(
        self,
        indicator_id: UUID,
        tenant_id: UUID,
        target_version: int,
    ) -> IndicatorRecord:
        """Create a new version whose DSL is identical to *target_version*'s DSL.

        Rollback NEVER mutates existing version rows — it creates a new version.

        Args:
            indicator_id: the indicator to roll back.
            tenant_id: tenant context.
            target_version: version number to restore.

        Returns:
            The updated IndicatorRecord with the new (incremented) version.

        Raises:
            ValueError: if target version or current indicator not found.
        """
        version_record = await self._repo.get_version(indicator_id, target_version)
        if version_record is None:
            raise ValueError(
                f"Version {target_version} not found for indicator {indicator_id}"
            )

        current = await self._repo.get_by_id(indicator_id, tenant_id)
        if current is None:
            raise ValueError(
                f"Indicator {indicator_id} not found for tenant {tenant_id}"
            )

        current.formula_dsl = version_record.formula_dsl
        current.updated_at = datetime.utcnow()
        return await self._repo.save(current)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _validate_dsl(self, formula_dsl: str, tenant_id: UUID) -> None:
        """Validate DSL formula; raise DslValidationError if invalid."""
        from src.scoring.dsl.tokenizer import tokenize
        from src.scoring.dsl.parser import parse

        tokens = tokenize(formula_dsl)
        ast = parse(tokens)
        result: ValidationResult = await self._validator.validate(ast, tenant_id)
        if not result.valid:
            raise DslValidationError(result.errors)

    @staticmethod
    def _compute_diff(dsl_old: str, dsl_new: str) -> DiffResult:
        """Compute token-level diff using difflib.SequenceMatcher."""
        try:
            old_tokens = [t.value for t in tokenize(dsl_old) if t.value]
            new_tokens = [t.value for t in tokenize(dsl_new) if t.value]
        except Exception:
            old_tokens = dsl_old.split()
            new_tokens = dsl_new.split()

        matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
        added: list[str] = []
        removed: list[str] = []
        unchanged: list[str] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                unchanged.extend(old_tokens[i1:i2])
            elif tag == "delete":
                removed.extend(old_tokens[i1:i2])
            elif tag == "insert":
                added.extend(new_tokens[j1:j2])
            elif tag == "replace":
                removed.extend(old_tokens[i1:i2])
                added.extend(new_tokens[j1:j2])

        return DiffResult(
            added_tokens=added,
            removed_tokens=removed,
            unchanged_tokens=unchanged,
        )
