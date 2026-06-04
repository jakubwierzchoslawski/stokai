"""Evaluator-level interfaces (Protocols) for dependency injection."""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class IFundamentalsProvider(Protocol):
    """Provides company fundamental data values for evaluation."""

    async def get_company_fundamentals(
        self, company_id: UUID, parameters: list[str]
    ) -> dict[str, float | None]: ...

    async def get_time_series(
        self, company_id: UUID, parameter: str, periods: int
    ) -> list[float | None]: ...


@runtime_checkable
class IParameterCatalog(Protocol):
    """Parameter catalog for validating DSL identifiers."""

    async def get_enabled_parameters(self, tenant_id: UUID) -> list[str]: ...
    async def get_parameter_definition(self, name: str, tenant_id: UUID) -> dict | None: ...
