"""Abstract base class for LLM providers.

Every concrete provider (OpenAI, Anthropic, Google, Ollama) must subclass
:class:`BaseLLM` and implement :meth:`chat`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from agent2.llm.message import LLMResponse, Message, ToolSchema


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
    """

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._extra = kwargs

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
