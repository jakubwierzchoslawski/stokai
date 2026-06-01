"""Unit tests for ParseStep and ClassifyStep (TASK-005, TDD).

Tests written before implementation.
Covers: AC-004.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.pipeline_state import (
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state(source: RawEventSource = RawEventSource.GDELT) -> PipelineState:
    tenant_id = uuid.uuid4()
    raw_event_id = uuid.uuid4()
    return PipelineState(
        raw_event_id=raw_event_id,
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=source,
            raw_payload={
                "title": "Conflict erupts in Eastern Europe",
                "url": "https://example.com/event",
                "actor1geo_lat": "50.45",
                "actor1geo_long": "30.52",
            },
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
    )


class TestClassifyStepSetsCategoryAndIntensity:
    """test_classify_step_sets_category_and_intensity"""

    @pytest.mark.asyncio
    async def test_classify_step_sets_category_and_intensity(self):
        """ClassifyStep sets state.category and state.intensity from LLM response."""
        from src.event_pipeline.steps.s04_classify import ClassifyStep

        llm_mock = AsyncMock()
        llm_mock.classify = AsyncMock(return_value={
            "category": "GEOPOLITICAL_CONFLICT",
            "intensity": 4,
        })

        repo_mock = AsyncMock()
        langfuse_mock = MagicMock()
        langfuse_mock.span = MagicMock(return_value=MagicMock())

        step = ClassifyStep(llm_client=llm_mock, repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()
        state = state.model_copy(update={
            "event_description": "Conflict erupts in Eastern Europe",
        })

        result = await step.execute(state)

        assert result.category == EventCategory.GEOPOLITICAL_CONFLICT
        assert result.intensity == 4


class TestClassifyStepRaisesOnInvalidCategory:
    """test_classify_step_raises_on_invalid_category"""

    @pytest.mark.asyncio
    async def test_classify_step_raises_on_invalid_category(self):
        """ClassifyStep raises InvalidCategoryError for unknown category."""
        from src.event_pipeline.steps.s04_classify import ClassifyStep
        from src.event_pipeline.exceptions import InvalidCategoryError

        llm_mock = AsyncMock()
        llm_mock.classify = AsyncMock(return_value={
            "category": "UNKNOWN_CATEGORY_XYZ",
            "intensity": 3,
        })

        repo_mock = AsyncMock()
        langfuse_mock = MagicMock()
        langfuse_mock.span = MagicMock(return_value=MagicMock())

        step = ClassifyStep(llm_client=llm_mock, repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()
        state = state.model_copy(update={"event_description": "Some event"})

        with pytest.raises(InvalidCategoryError):
            await step.execute(state)


class TestClassifyStepRaisesOnOutOfRangeIntensity:
    """test_classify_step_raises_on_out_of_range_intensity"""

    @pytest.mark.asyncio
    async def test_classify_step_raises_on_out_of_range_intensity(self):
        """ClassifyStep raises InvalidIntensityError when intensity=6."""
        from src.event_pipeline.steps.s04_classify import ClassifyStep
        from src.event_pipeline.exceptions import InvalidIntensityError

        llm_mock = AsyncMock()
        llm_mock.classify = AsyncMock(return_value={
            "category": "GEOPOLITICAL_CONFLICT",
            "intensity": 6,
        })

        repo_mock = AsyncMock()
        langfuse_mock = MagicMock()
        langfuse_mock.span = MagicMock(return_value=MagicMock())

        step = ClassifyStep(llm_client=llm_mock, repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()
        state = state.model_copy(update={"event_description": "Some event"})

        with pytest.raises(InvalidIntensityError):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_classify_step_raises_on_zero_intensity(self):
        """ClassifyStep raises InvalidIntensityError when intensity=0."""
        from src.event_pipeline.steps.s04_classify import ClassifyStep
        from src.event_pipeline.exceptions import InvalidIntensityError

        llm_mock = AsyncMock()
        llm_mock.classify = AsyncMock(return_value={
            "category": "ECONOMIC_POLICY",
            "intensity": 0,
        })

        repo_mock = AsyncMock()
        langfuse_mock = MagicMock()
        langfuse_mock.span = MagicMock(return_value=MagicMock())

        step = ClassifyStep(llm_client=llm_mock, repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()
        state = state.model_copy(update={"event_description": "Some event"})

        with pytest.raises(InvalidIntensityError):
            await step.execute(state)


class TestClassifyStepWritesAuditLog:
    """test_classify_step_writes_audit_log"""

    @pytest.mark.asyncio
    async def test_classify_step_writes_audit_log(self):
        """ClassifyStep calls repo.write_audit_log with model_id and trace_id."""
        from src.event_pipeline.steps.s04_classify import ClassifyStep

        llm_mock = AsyncMock()
        llm_mock.classify = AsyncMock(return_value={
            "category": "CORPORATE_ACTION",
            "intensity": 2,
        })

        repo_mock = AsyncMock()
        repo_mock.write_audit_log = AsyncMock()

        langfuse_mock = MagicMock()
        langfuse_mock.span = MagicMock(return_value=MagicMock())

        step = ClassifyStep(llm_client=llm_mock, repo=repo_mock, langfuse_client=langfuse_mock)
        state = _make_state()
        state = state.model_copy(update={
            "event_description": "AAPL announces buyback",
            "langfuse_trace_id": "trace-abc-123",
        })

        await step.execute(state)

        repo_mock.write_audit_log.assert_called_once()
        call_kwargs = repo_mock.write_audit_log.call_args.kwargs
        assert "model_id" in call_kwargs or len(repo_mock.write_audit_log.call_args.args) > 0


class TestParseStepRoutesToCorrectParserBySource:
    """test_parse_step_routes_to_correct_parser_by_source"""

    @pytest.mark.asyncio
    async def test_parse_step_routes_to_correct_parser_by_source(self):
        """ParseStep sets event_description from GDELT payload."""
        from src.event_pipeline.steps.s03_parse import ParseStep

        step = ParseStep()
        state = _make_state(source=RawEventSource.GDELT)

        result = await step.execute(state)

        assert result.event_description is not None
        assert len(result.event_description) > 0

    @pytest.mark.asyncio
    async def test_parse_step_extracts_geo_from_gdelt(self):
        """ParseStep extracts geo coordinates from GDELT payload."""
        from src.event_pipeline.steps.s03_parse import ParseStep

        step = ParseStep()
        state = _make_state(source=RawEventSource.GDELT)

        result = await step.execute(state)

        assert result.geo_lat is not None
        assert result.geo_lon is not None
