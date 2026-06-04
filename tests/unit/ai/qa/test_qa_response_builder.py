"""
Unit tests for QAResponseBuilder (PLAN-F-027 TASK-003).

Tests:
  - build returns QAAnswer with answer_text, sources, confidence, cost_usd
  - cost_limited=True sets flag and trims sources to max 3
  - confidence is clamped to [0.0, 1.0]
  - missing optional fields fall back gracefully
  - sources extracted from nested supporting_data.sources key
"""
from __future__ import annotations

import pytest

from src.ai.qa.response_builder import QAAnswer, QAResponseBuilder, QASource


@pytest.fixture
def builder() -> QAResponseBuilder:
    return QAResponseBuilder()


@pytest.fixture
def full_agent_output() -> dict:
    return {
        "answer": "Your AAPL exposure is 15% of your portfolio.",
        "confidence": 0.87,
        "sources": [
            {"type": "event", "id": "evt-001", "description": "AAPL Q1 2026 earnings"},
            {"type": "filing", "id": "fil-042", "description": "AAPL 10-K 2025"},
            {"type": "price_bar", "id": "pb-99", "description": "AAPL close 2026-06-01"},
            {"type": "recommendation", "id": "rec-7", "description": "Prior AAPL buy rec"},
        ],
    }


class TestQAResponseBuilderBuild:
    """QAResponseBuilder.build() returns correct QAAnswer."""

    def test_build_returns_qa_answer(self, builder, full_agent_output):
        """build() returns a QAAnswer instance."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.12)
        assert isinstance(result, QAAnswer)

    def test_build_answer_text(self, builder, full_agent_output):
        """build() extracts answer_text from agent output."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.12)
        assert result.answer_text == "Your AAPL exposure is 15% of your portfolio."

    def test_build_confidence(self, builder, full_agent_output):
        """build() extracts confidence from agent output."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.12)
        assert result.confidence == pytest.approx(0.87)

    def test_build_cost_usd(self, builder, full_agent_output):
        """build() sets cost_usd from accumulated_cost param."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.25)
        assert result.cost_usd == pytest.approx(0.25)

    def test_build_sources_list(self, builder, full_agent_output):
        """build() extracts sources list."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.12)
        assert len(result.sources) == 4
        assert result.sources[0].type == "event"
        assert result.sources[0].id == "evt-001"
        assert "earnings" in result.sources[0].description

    def test_build_cost_limited_false(self, builder, full_agent_output):
        """build() sets cost_limited=False when not limited."""
        result = builder.build(full_agent_output, cost_limited=False, accumulated_cost=0.12)
        assert result.cost_limited is False

    def test_build_cost_limited_true_sets_flag(self, builder, full_agent_output):
        """build() with cost_limited=True sets QAAnswer.cost_limited=True."""
        result = builder.build(full_agent_output, cost_limited=True, accumulated_cost=0.41)
        assert result.cost_limited is True

    def test_build_cost_limited_trims_sources(self, builder, full_agent_output):
        """build() with cost_limited=True trims sources to max 3."""
        result = builder.build(full_agent_output, cost_limited=True, accumulated_cost=0.41)
        assert len(result.sources) <= 3

    def test_build_cost_limited_keeps_first_sources(self, builder, full_agent_output):
        """cost_limited=True keeps the first N sources (most relevant first)."""
        result = builder.build(full_agent_output, cost_limited=True, accumulated_cost=0.41)
        # The first source should still be the AAPL earnings event
        assert result.sources[0].id == "evt-001"


class TestQAResponseBuilderFallbacks:
    """build() falls back gracefully for missing fields."""

    def test_missing_answer_defaults_to_empty_string(self, builder):
        """Missing 'answer' key → answer_text=''."""
        result = builder.build({}, cost_limited=False, accumulated_cost=0.0)
        assert result.answer_text == ""

    def test_missing_confidence_defaults_to_zero(self, builder):
        """Missing 'confidence' key → confidence=0.0."""
        result = builder.build({"answer": "Test"}, cost_limited=False, accumulated_cost=0.0)
        assert result.confidence == pytest.approx(0.0)

    def test_missing_sources_defaults_to_empty_list(self, builder):
        """Missing 'sources' key → sources=[]."""
        result = builder.build({"answer": "Test", "confidence": 0.5},
                               cost_limited=False, accumulated_cost=0.0)
        assert result.sources == []

    def test_confidence_clamped_above_one(self, builder):
        """Confidence > 1.0 is clamped to 1.0."""
        result = builder.build(
            {"answer": "Test", "confidence": 1.5}, cost_limited=False, accumulated_cost=0.0
        )
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_clamped_below_zero(self, builder):
        """Confidence < 0.0 is clamped to 0.0."""
        result = builder.build(
            {"answer": "Test", "confidence": -0.3}, cost_limited=False, accumulated_cost=0.0
        )
        assert result.confidence == pytest.approx(0.0)

    def test_malformed_source_entry_skipped(self, builder):
        """Malformed source entries (non-dict) are silently skipped."""
        output = {
            "answer": "Test",
            "sources": [
                "not-a-dict",
                {"type": "event", "id": "evt-1", "description": "Valid"},
                None,
            ],
        }
        result = builder.build(output, cost_limited=False, accumulated_cost=0.0)
        # Only the valid dict entry survives
        assert len(result.sources) == 1
        assert result.sources[0].id == "evt-1"


class TestQAResponseBuilderNestedSources:
    """Sources extracted from supporting_data.sources fallback key."""

    def test_sources_from_supporting_data(self, builder):
        """When top-level 'sources' absent, falls back to supporting_data.sources."""
        output = {
            "answer": "AAPL exposure is 10%.",
            "confidence": 0.75,
            "supporting_data": {
                "sources": [
                    {"type": "semantic_fact", "id": "sf-3", "description": "AAPL sector note"}
                ]
            },
        }
        result = builder.build(output, cost_limited=False, accumulated_cost=0.0)
        assert len(result.sources) == 1
        assert result.sources[0].type == "semantic_fact"
        assert result.sources[0].id == "sf-3"

    def test_top_level_sources_takes_priority_over_supporting_data(self, builder):
        """Top-level 'sources' key takes precedence over supporting_data.sources."""
        output = {
            "answer": "Test",
            "sources": [
                {"type": "event", "id": "top-level", "description": "Top level source"}
            ],
            "supporting_data": {
                "sources": [
                    {"type": "filing", "id": "nested", "description": "Nested source"}
                ]
            },
        }
        result = builder.build(output, cost_limited=False, accumulated_cost=0.0)
        assert len(result.sources) == 1
        assert result.sources[0].id == "top-level"
