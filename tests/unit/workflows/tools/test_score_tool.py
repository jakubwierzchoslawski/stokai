"""TDD tests for GetEventExposureScoreTool (PLAN-F-003 TASK-012).

Tests written before implementation (red phase).
AC-006: Tool output at most 50 rows, Pydantic-typed, tenant-scoped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.scoring.interfaces import ScoreResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_score_result(tenant_id: uuid.UUID) -> ScoreResult:
    return ScoreResult(
        score_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        indicator_id=uuid.uuid4(),
        indicator_version_id=uuid.uuid4(),
        score=1.0,
        geo_weight_applied=1.0,
        inputs_hash="hash123",
        computed_at=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


def _make_tool(mock_scores: list[ScoreResult]):
    from src.workflows.tools.score_tool import GetEventExposureScoreTool

    repo = AsyncMock()
    repo.get_latest.return_value = mock_scores
    return GetEventExposureScoreTool(repository=repo), repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetEventExposureScoreTool:

    @pytest.mark.asyncio
    async def test_output_is_pydantic_typed(self):
        """Tool output is an instance of GetEventExposureScoreOutput."""
        from src.workflows.tools.score_tool import (
            GetEventExposureScoreInput,
            GetEventExposureScoreOutput,
        )
        tenant_id = uuid.uuid4()
        scores = [_make_score_result(tenant_id) for _ in range(3)]
        tool, _ = _make_tool(scores)

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=10)
        output = await tool.execute(inp)

        assert isinstance(output, GetEventExposureScoreOutput)

    @pytest.mark.asyncio
    async def test_limit_hard_capped_at_50(self):
        """Passing limit=100 results in at most 50 rows."""
        from src.workflows.tools.score_tool import GetEventExposureScoreInput

        tenant_id = uuid.uuid4()
        scores = [_make_score_result(tenant_id) for _ in range(50)]
        tool, repo = _make_tool(scores)

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=100)
        output = await tool.execute(inp)

        assert len(output.scores) <= 50
        # Verify the repository was called with limit <= 50
        call_args = repo.get_latest.call_args
        query = call_args[0][0]
        assert query.limit <= 50

    @pytest.mark.asyncio
    async def test_truncated_flag_set_when_results_exceed_limit(self):
        """Mock repo returns 51 results; truncated=True and len(scores)==50."""
        from src.workflows.tools.score_tool import GetEventExposureScoreInput

        tenant_id = uuid.uuid4()
        # We mock 51 items, but repo's get_latest should cap at 50 in real impl.
        # To test truncated, the tool performs a sentinel count query.
        scores_50 = [_make_score_result(tenant_id) for _ in range(50)]
        tool, repo = _make_tool(scores_50)

        # Patch the tool to simulate a count that indicates there are more
        # The tool implementation detects truncation by querying limit+1
        # and checking if count == limit + 1
        scores_51 = [_make_score_result(tenant_id) for _ in range(51)]
        # First call returns 51 (sentinel), second returns 50 (actual)
        repo.get_latest.side_effect = [scores_51, scores_50]

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=50)
        output = await tool.execute(inp)

        assert output.truncated is True
        assert len(output.scores) <= 50

    @pytest.mark.asyncio
    async def test_not_truncated_when_results_under_limit(self):
        """3 results with limit=50 → truncated=False."""
        from src.workflows.tools.score_tool import GetEventExposureScoreInput

        tenant_id = uuid.uuid4()
        scores = [_make_score_result(tenant_id) for _ in range(3)]
        # Sentinel query returns same 3 (not 51)
        tool, repo = _make_tool(scores)
        repo.get_latest.side_effect = [scores, scores]

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=50)
        output = await tool.execute(inp)

        assert output.truncated is False

    @pytest.mark.asyncio
    async def test_empty_result_raises_insufficient_data(self):
        """No score records → raises InsufficientDataError."""
        from src.scoring.exceptions import InsufficientDataError
        from src.workflows.tools.score_tool import GetEventExposureScoreInput

        tenant_id = uuid.uuid4()
        tool, repo = _make_tool([])
        repo.get_latest.side_effect = [[]]

        inp = GetEventExposureScoreInput(tenant_id=tenant_id)

        with pytest.raises(InsufficientDataError):
            await tool.execute(inp)

    @pytest.mark.asyncio
    async def test_scores_list_contains_score_result_instances(self):
        """Each item in output.scores is a ScoreResult."""
        from src.workflows.tools.score_tool import GetEventExposureScoreInput

        tenant_id = uuid.uuid4()
        scores = [_make_score_result(tenant_id) for _ in range(5)]
        tool, repo = _make_tool(scores)
        repo.get_latest.side_effect = [scores, scores]

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=10)
        output = await tool.execute(inp)

        for item in output.scores:
            assert isinstance(item, ScoreResult)

    @pytest.mark.asyncio
    async def test_cross_tenant_access_raises_tool_not_applicable(self):
        """tenant_id mismatch in context raises ToolNotApplicable."""
        from src.workflows.tools.score_tool import (
            GetEventExposureScoreInput,
            ToolNotApplicable,
        )

        tenant_id = uuid.uuid4()
        caller_tenant_id = uuid.uuid4()  # Different tenant
        scores = [_make_score_result(tenant_id)]
        tool, _ = _make_tool(scores)

        inp = GetEventExposureScoreInput(tenant_id=tenant_id, limit=10)

        with pytest.raises(ToolNotApplicable):
            await tool.execute(inp, calling_tenant_id=caller_tenant_id)
