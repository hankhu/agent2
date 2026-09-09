"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from agent2.llm.message import LLMResponse, Message, ToolSchema, Usage
from agent2.llm.pricing import ModelPricing, guess_pricing


# ── Context window lookup ──────────────────────────────────────────

# (model substring, context window in tokens) — first match wins, so more
# specific prefixes must come before generic ones.
_CONTEXT_WINDOWS: tuple[tuple[str, int], ...] = (
    ("gpt-4.1", 1_000_000),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-4", 8_192),
    ("gpt-3.5", 16_385),
    ("o1-mini", 128_000),
    ("o1-", 200_000),
    ("o1", 200_000),
    ("o3-mini", 200_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("deepseek-v4", 1_000_000),
    ("deepseek-reasoner", 64_000),
    ("deepseek-r1", 64_000),
    ("deepseek", 128_000),
    ("claude-3-7", 200_000),
    ("claude-3-5", 200_000),
    ("claude", 200_000),
    ("gemini-2.0", 1_000_000),
    ("gemini-1.5", 1_000_000),
    ("gemini", 1_000_000),
    ("llama-3.3", 128_000),
    ("llama-3.2", 128_000),
    ("llama-3.1", 128_000),
    ("llama3.1", 128_000),
    ("llama3", 8_192),
    ("qwen2.5", 128_000),
    ("qwen", 128_000),
    ("mistral", 128_000),
    ("kimi", 128_000),
    ("glm-4", 128_000),
    ("moonshot", 128_000),
)

DEFAULT_CONTEXT_WINDOW = 128_000


def guess_context_window(model: str) -> int:
    """Best-effort context window (in tokens) for a model name."""
    m = (model or "").lower()
    for prefix, window in _CONTEXT_WINDOWS:
        if m.startswith(prefix):
            return window
    return DEFAULT_CONTEXT_WINDOW


class BaseLLM(ABC):
    """Unified interface for large language model providers.

    Parameters
    ----------
    model : str
        Model identifier (e.g. ``"gpt-4o-mini"``, ``"claude-sonnet-4-20250514"``).
    temperature : float
        Sampling temperature.
    max_tokens : int
        Maximum tokens to generate.
    context_window : int | None
        Context window size in tokens. If omitted, guessed from the model name.
    top_k : int | None
        Top-k sampling parameter.
    top_p : float | None
        Top-p (nucleus) sampling parameter.
    reasoning_effort : str | None
        Constrains effort on reasoning models (e.g. ``"low"``, ``"medium"``, ``"high"``).
    pricing : ModelPricing | dict[str, Any] | None
        Pricing configuration for token usage cost estimation.
    """

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        context_window: int | None = None,
        top_k: int | None = None,
        top_p: float | None = None,
        reasoning_effort: str | None = None,
        pricing: ModelPricing | dict[str, Any] | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.context_window = context_window or guess_context_window(model)
        self.top_k = top_k
        self.top_p = top_p
        self.reasoning_effort = reasoning_effort

        if isinstance(pricing, ModelPricing):
            self.pricing = pricing
        elif isinstance(pricing, dict):
            self.pricing = ModelPricing(
                input_cost_per_million=pricing.get("input", pricing.get("input_cost_per_million", 0.0)),
                output_cost_per_million=pricing.get("output", pricing.get("output_cost_per_million", 0.0)),
                currency=pricing.get("currency", "USD"),
            )
        else:
            self.pricing = guess_pricing(model)

        # Usage & Cost tracking — updated by subclasses after each request.
        self.last_usage: Usage | None = None
        self.total_usage: Usage = Usage()
        self.last_cost: float = 0.0
        self.total_cost: float = 0.0
        self._extra = kwargs

    def _record_usage(self, usage: Usage | None) -> None:
        """Record usage from the most recent request and accumulate totals."""
        if usage is None:
            return
        self.last_usage = usage
        self.total_usage = self.total_usage + usage
        cost = self.pricing.calculate_cost(usage.prompt_tokens, usage.completion_tokens)
        self.last_cost = cost
        self.total_cost = round(self.total_cost + cost, 6)

    # ── Core interface ──────────────────────────────────────────────

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send messages to the LLM and return a normalised response.

        Parameters
        ----------
        messages : list[Message]
            Conversation history.
        tools : list[ToolSchema] | None
            Available tools the LLM may call.

        Returns
        -------
        LLMResponse
            Normalised response containing the assistant message and usage.
        """
        ...

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response tokens. Default implementation falls back to chat().

        Subclasses may override for true streaming support.
        """
        response = await self.chat(messages, tools=tools, **kwargs)
        if response.content:
            yield response.content

    # ── Helpers ─────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r})"
