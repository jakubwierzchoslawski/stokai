"""
Unit tests for LLMPricingTable (TDD — written before implementation).

Covers MODEL_PRICES for claude-haiku-4-5, claude-sonnet-4-6,
and text-embedding-3-small. Validates correct cost computation,
error cases, and the max-budget-below-ceiling property.
"""
from __future__ import annotations

import pytest

from src.event_pipeline.pricing import LLMPricingTable


class TestComputeHaikuClassifyBudget:
    def test_compute_haiku_classify_budget(self) -> None:
        """Haiku 4.5: 2000 input + 200 output tokens should produce correct cost."""
        cost = LLMPricingTable.compute("claude-haiku-4-5", 2000, 200)
        # input: 2000 * 0.00025/1000 = 0.0005
        # output: 200 * 0.00125/1000 = 0.00025
        # total: 0.00075
        assert abs(cost - 0.00075) < 1e-9


class TestComputeSonnetAlertBudget:
    def test_compute_sonnet_alert_budget(self) -> None:
        """Sonnet 4.6: 3000 input + 200 output tokens should produce correct cost."""
        cost = LLMPricingTable.compute("claude-sonnet-4-6", 3000, 200)
        # input: 3000 * 0.003/1000 = 0.009
        # output: 200 * 0.015/1000 = 0.003
        # total: 0.012
        assert abs(cost - 0.012) < 1e-9


class TestComputeEmbeddingNoOutputTokens:
    def test_compute_embedding_no_output_tokens(self) -> None:
        """Embedding model only uses input tokens (output rate is 0.0)."""
        cost = LLMPricingTable.compute("text-embedding-3-small", 500, 0)
        # input: 500 * 0.00002/1000 = 0.00001
        # output: 0
        # total: 0.00001
        assert abs(cost - 0.00001) < 1e-9

    def test_compute_embedding_with_output_tokens_still_zero_output_cost(self) -> None:
        """Embedding model output rate is 0.0 — even passing output_tokens > 0 costs nothing."""
        cost_with_output = LLMPricingTable.compute("text-embedding-3-small", 500, 100)
        cost_without_output = LLMPricingTable.compute("text-embedding-3-small", 500, 0)
        assert cost_with_output == cost_without_output


class TestComputeUnknownModelRaisesValueError:
    def test_compute_unknown_model_raises_value_error(self) -> None:
        """Unknown model_id must raise ValueError."""
        with pytest.raises(ValueError, match="unknown model"):
            LLMPricingTable.compute("gpt-4o", 100, 10)


class TestComputeNegativeTokensRaisesValueError:
    def test_compute_negative_tokens_raises_value_error(self) -> None:
        """Negative input_tokens must raise ValueError."""
        with pytest.raises(ValueError, match="negative"):
            LLMPricingTable.compute("claude-haiku-4-5", -1, 0)

    def test_compute_negative_output_tokens_raises_value_error(self) -> None:
        """Negative output_tokens must raise ValueError."""
        with pytest.raises(ValueError, match="negative"):
            LLMPricingTable.compute("claude-haiku-4-5", 100, -1)


class TestSupportedModelsReturnsAllThree:
    def test_supported_models_returns_all_three(self) -> None:
        """supported_models() returns all three model keys."""
        models = LLMPricingTable.supported_models()
        assert "claude-haiku-4-5" in models
        assert "claude-sonnet-4-6" in models
        assert "text-embedding-3-small" in models
        assert len(models) == 3


class TestMaxBudgetScenarioBelowCeiling:
    def test_max_budget_scenario_below_ceiling(self) -> None:
        """Max token budgets (classify+extract+embed+alert) must stay < $0.05."""
        # Haiku classify: 2k in, 200 out
        cost_classify = LLMPricingTable.compute("claude-haiku-4-5", 2000, 200)
        # Haiku extract: 1k in, 100 out
        cost_extract = LLMPricingTable.compute("claude-haiku-4-5", 1000, 100)
        # Embedding: 500 in
        cost_embed = LLMPricingTable.compute("text-embedding-3-small", 500, 0)
        # Sonnet alert: 3k in, 200 out
        cost_alert = LLMPricingTable.compute("claude-sonnet-4-6", 3000, 200)

        total = cost_classify + cost_extract + cost_embed + cost_alert
        assert total < 0.05, (
            f"Max budget scenario total ${total:.6f} must be < $0.05 (hard ceiling)"
        )
