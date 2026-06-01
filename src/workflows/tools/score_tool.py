"""GetEventExposureScoreTool — Tool Library read tool (PLAN-F-003 TASK-012).

Provides typed, tenant-scoped, 50-row-capped access to scored exposure results.

Contracts (ARCHITECTURE.md §8, REQ-N-005):
    - Input:  GetEventExposureScoreInput (Pydantic)
    - Output: GetEventExposureScoreOutput (Pydantic)
    - Max rows returned: 50 (hard ceiling, not merely a default)
    - Tenant isolation: calling_tenant_id must match input.tenant_id
    - Read-only: never mutates score_records

Error types:
    ToolNotApplicable     — tenant_id mismatch (cross-tenant access attempt)
    InsufficientDataError — no score records found for the given query

Truncation detection (AC-006):
    The tool performs a sentinel query with limit+1.  If the repository
    returns limit+1 rows then there are more results than requested, so
    ``truncated=True``.  The first ``limit`` rows are returned.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.scoring.exceptions import InsufficientDataError
from src.scoring.interfaces import ScoreQuery, ScoreResult

if TYPE_CHECKING:
    pass

_MAX_ROWS = 50


class ToolNotApplicable(Exception):
    """Raised when the calling agent's tenant does not match the query tenant_id.

    Follows the Tool Library contract from ARCHITECTURE.md §8:
    'Cross-tenant tool calls are rejected with ToolNotApplicable.'
    """


class GetEventExposureScoreInput(BaseModel):
    """Input model for the get_event_exposure_score tool.

    Attributes
    ----------
    tenant_id:
        The tenant whose score records are being queried. Required.
    company_ids:
        Optional list of company UUIDs to filter by.
    indicator_id:
        Optional indicator UUID to filter by.
    computed_at_from:
        Optional lower bound for computed_at (inclusive).
    computed_at_to:
        Optional upper bound for computed_at (inclusive).
    limit:
        Maximum number of rows to return. Hard-capped at 50 regardless of value.
    """

    tenant_id: uuid.UUID
    company_ids: list[uuid.UUID] | None = None
    indicator_id: uuid.UUID | None = None
    computed_at_from: datetime | None = None
    computed_at_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)  # tool accepts up to 100; internally caps at 50


class GetEventExposureScoreOutput(BaseModel):
    """Output model for the get_event_exposure_score tool.

    Attributes
    ----------
    scores:
        List of ScoreResult objects, len(scores) <= 50 always.
    truncated:
        True when the backing data has more results than the requested limit.
    """

    scores: list[ScoreResult]
    truncated: bool


class GetEventExposureScoreTool:
    """Read-only Tool Library entry for querying event exposure scores.

    Parameters
    ----------
    repository:
        Injected ``ScoreRepository`` (or compatible async object with
        ``get_latest`` method). Never imported directly (DIP).
    """

    def __init__(self, repository: object) -> None:
        self._repository = repository

    async def execute(
        self,
        input_model: GetEventExposureScoreInput,
        calling_tenant_id: uuid.UUID | None = None,
    ) -> GetEventExposureScoreOutput:
        """Execute the tool and return scored results.

        Parameters
        ----------
        input_model:
            The typed input parameters.
        calling_tenant_id:
            The tenant context of the calling agent. When provided, must
            match ``input_model.tenant_id`` or ``ToolNotApplicable`` is raised.

        Returns
        -------
        GetEventExposureScoreOutput
            Typed output with at most 50 score records and a truncation flag.

        Raises
        ------
        ToolNotApplicable
            When ``calling_tenant_id`` is provided and differs from
            ``input_model.tenant_id``.
        InsufficientDataError
            When no score records exist for the given query parameters.
        """
        # Tenant isolation check (ARCHITECTURE.md §8, D3)
        if calling_tenant_id is not None and calling_tenant_id != input_model.tenant_id:
            raise ToolNotApplicable(
                f"Tenant mismatch: calling tenant {calling_tenant_id!r} is not "
                f"permitted to access scores for tenant {input_model.tenant_id!r}."
            )

        # Hard-cap at 50 rows regardless of input.limit
        effective_limit = min(input_model.limit, _MAX_ROWS)

        # Sentinel query: request limit+1 to detect truncation
        sentinel_limit = min(effective_limit + 1, _MAX_ROWS + 1)

        sentinel_query = ScoreQuery(
            tenant_id=input_model.tenant_id,
            company_ids=input_model.company_ids,
            indicator_id=input_model.indicator_id,
            computed_at_from=input_model.computed_at_from,
            computed_at_to=input_model.computed_at_to,
            limit=min(sentinel_limit, 50),  # ScoreQuery hard-caps at 50
        )
        sentinel_rows = await self._repository.get_latest(sentinel_query)

        # Check for InsufficientData
        if not sentinel_rows:
            raise InsufficientDataError(
                f"No score records found for tenant {input_model.tenant_id!r} "
                "with the given query parameters."
            )

        # Truncation detection
        if len(sentinel_rows) > effective_limit:
            truncated = True
            # Fetch the actual result set
            actual_query = ScoreQuery(
                tenant_id=input_model.tenant_id,
                company_ids=input_model.company_ids,
                indicator_id=input_model.indicator_id,
                computed_at_from=input_model.computed_at_from,
                computed_at_to=input_model.computed_at_to,
                limit=effective_limit,
            )
            scores = list(await self._repository.get_latest(actual_query))
        else:
            truncated = False
            scores = list(sentinel_rows[:effective_limit])

        return GetEventExposureScoreOutput(
            scores=scores,
            truncated=truncated,
        )
