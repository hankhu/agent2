"""Model pricing information and cost estimation."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    """Pricing configuration for token usage (rates per 1 million tokens in USD)."""

    input_cost_per_million: float = Field(
        default=0.0,
        description="Cost in USD per 1 million input (prompt) tokens",
    )
    output_cost_per_million: float = Field(
        default=0.0,
        description="Cost in USD per 1 million output (completion) tokens",
    )
    currency: str = Field(
        default="USD",
        description="Currency code (default USD)",
    )

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate total estimated cost for given prompt and completion tokens."""
        if self.input_cost_per_million <= 0 and self.output_cost_per_million <= 0:
            return 0.0
        cost = (
            prompt_tokens * self.input_cost_per_million
            + completion_tokens * self.output_cost_per_million
        ) / 1_000_000.0
        return round(cost, 6)

    def format_rate(self) -> str:
        """Format a human-readable rate string, e.g. '$0.15/$0.60/1M'."""
        if self.input_cost_per_million <= 0 and self.output_cost_per_million <= 0:
            return "Free"
        inp = f"{self.input_cost_per_million:g}"
        out = f"{self.output_cost_per_million:g}"
        curr = "$" if self.currency == "USD" else f"{self.currency} "
        return f"{curr}{inp}/{curr}{out}/1M"


# (model prefix, ModelPricing)
_DEFAULT_PRICING: tuple[tuple[str, ModelPricing], ...] = (
    ("gpt-4o-mini", ModelPricing(input_cost_per_million=0.15, output_cost_per_million=0.60)),
    ("gpt-4o", ModelPricing(input_cost_per_million=2.50, output_cost_per_million=10.00)),
    ("gpt-4-turbo", ModelPricing(input_cost_per_million=10.00, output_cost_per_million=30.00)),
    ("gpt-4.1", ModelPricing(input_cost_per_million=2.00, output_cost_per_million=8.00)),
    ("gpt-3.5-turbo", ModelPricing(input_cost_per_million=0.50, output_cost_per_million=1.50)),
    ("o1-mini", ModelPricing(input_cost_per_million=1.10, output_cost_per_million=4.40)),
    ("o1", ModelPricing(input_cost_per_million=15.00, output_cost_per_million=60.00)),
    ("o3-mini", ModelPricing(input_cost_per_million=1.10, output_cost_per_million=4.40)),
    ("o3", ModelPricing(input_cost_per_million=1.10, output_cost_per_million=4.40)),
    ("claude-3-7-sonnet", ModelPricing(input_cost_per_million=3.00, output_cost_per_million=15.00)),
    ("claude-3-5-sonnet", ModelPricing(input_cost_per_million=3.00, output_cost_per_million=15.00)),
    ("claude-3-5-haiku", ModelPricing(input_cost_per_million=0.80, output_cost_per_million=4.00)),
    ("claude-3-opus", ModelPricing(input_cost_per_million=15.00, output_cost_per_million=75.00)),
    ("deepseek-reasoner", ModelPricing(input_cost_per_million=0.55, output_cost_per_million=2.19)),
    ("deepseek-r1", ModelPricing(input_cost_per_million=0.55, output_cost_per_million=2.19)),
    ("deepseek-chat", ModelPricing(input_cost_per_million=0.14, output_cost_per_million=0.28)),
    ("deepseek-v4", ModelPricing(input_cost_per_million=0.14, output_cost_per_million=0.28)),
    ("deepseek-v3", ModelPricing(input_cost_per_million=0.14, output_cost_per_million=0.28)),
    ("gemini-2.0-flash", ModelPricing(input_cost_per_million=0.10, output_cost_per_million=0.40)),
    ("gemini-2.5-pro", ModelPricing(input_cost_per_million=1.25, output_cost_per_million=5.00)),
    ("gemini-1.5-pro", ModelPricing(input_cost_per_million=1.25, output_cost_per_million=5.00)),
    ("gemini-1.5-flash", ModelPricing(input_cost_per_million=0.075, output_cost_per_million=0.30)),
    ("qwen-plus", ModelPricing(input_cost_per_million=0.40, output_cost_per_million=1.20)),
    ("qwen-turbo", ModelPricing(input_cost_per_million=0.05, output_cost_per_million=0.20)),
    ("qwen-max", ModelPricing(input_cost_per_million=1.60, output_cost_per_million=6.40)),
    ("llama", ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0)),
    ("ollama", ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0)),
)


def guess_pricing(model: str) -> ModelPricing:
    """Guess model pricing based on model name prefix."""
    m = (model or "").lower()
    for prefix, pricing in _DEFAULT_PRICING:
        if m.startswith(prefix):
            return pricing
    return ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0)
