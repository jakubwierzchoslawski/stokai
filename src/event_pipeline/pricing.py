"""
LLMPricingTable — static pricing registry for LLM and embedding models.

TOKEN BUDGET ANALYSIS (max possible cost per pipeline run):
  - classify_event  (claude-haiku-4-5):    2000 in + 200 out  = $0.000750
  - extract_tickers (claude-haiku-4-5):    1000 in + 100 out  = $0.000375
  - embed_event     (text-embedding-3-small): 500 in           = $0.000010
  - generate_alert  (claude-sonnet-4-6):   3000 in + 200 out  = $0.012000

  TOTAL MAX BUDGET = $0.013135  <  $0.050000 hard ceiling  ✓
"""
from __future__ import annotations

# USD per 1 000 tokens for each model.
# Structure: {model_id: {"input": rate_per_1k, "output": rate_per_1k}}
MODEL_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 0.00025, "output": 0.00125},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
}


class LLMPricingTable:
    """Static pricing table for LLM and embedding models.

    All methods are class-level; no instance is required.

    Token budget analysis (worst-case per pipeline run):
      classify (Haiku):  2 000 in / 200 out  → $0.000 750
      extract  (Haiku):  1 000 in / 100 out  → $0.000 375
      embed    (OpenAI):   500 in /   0 out  → $0.000 010
      alert    (Sonnet): 3 000 in / 200 out  → $0.012 000
      ─────────────────────────────────────
      TOTAL MAX                              → $0.013 135  < $0.05 ceiling
    """

    @classmethod
    def compute(cls, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Return the USD cost for *input_tokens* + *output_tokens* on *model_id*.

        Args:
            model_id: One of the keys in MODEL_PRICES.
            input_tokens: Number of prompt/input tokens (must be >= 0).
            output_tokens: Number of completion/output tokens (must be >= 0).

        Returns:
            Cost in USD (a non-negative float).

        Raises:
            ValueError: If model_id is not in MODEL_PRICES.
            ValueError: If either token count is negative.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError(
                f"Token counts must be non-negative; "
                f"got input_tokens={input_tokens}, output_tokens={output_tokens}"
            )
        if model_id not in MODEL_PRICES:
            raise ValueError(
                f"LLMPricingTable: unknown model {model_id!r}. "
                f"Supported models: {list(MODEL_PRICES)}"
            )
        rates = MODEL_PRICES[model_id]
        input_cost = input_tokens * rates["input"] / 1000.0
        output_cost = output_tokens * rates["output"] / 1000.0
        return input_cost + output_cost

    @classmethod
    def supported_models(cls) -> list[str]:
        """Return a list of all supported model identifiers.

        Returns:
            List of model_id strings (order matches MODEL_PRICES insertion order).
        """
        return list(MODEL_PRICES.keys())
