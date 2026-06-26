"""LLM abstraction layer — unified interface for multiple providers.

Quick start::

    from agent2.llm import create_llm, Message

    llm = create_llm("openai", model="gpt-4o-mini")
    response = await llm.chat([Message.user("Hello!")])
    print(response.content)
"""

from __future__ import annotations

from typing import Any

from agent2.llm.base import BaseLLM
from agent2.llm.message import (
    LLMResponse,
    Message,
    Role,
    ToolCall,
    ToolResult,
    ToolSchema,
    ToolParameter,
    Usage,
)

__all__ = [
    "BaseLLM",
    "LLMResponse",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "ToolSchema",
    "ToolParameter",
    "Usage",
    "create_llm",
]


def create_llm(provider: str, **kwargs: Any) -> BaseLLM:
    """Factory function to create an LLM instance by provider name.

    Parameters
    ----------
    provider : str
        One of ``"openai"``, ``"anthropic"``, ``"google"``, ``"ollama"``.
    **kwargs
        Passed directly to the provider constructor.

    Returns
    -------
    BaseLLM
        A configured LLM instance.

    Examples
    --------
    >>> llm = create_llm("openai", model="gpt-4o")
    >>> llm = create_llm("anthropic", model="claude-sonnet-4-20250514")
    >>> llm = create_llm("ollama", model="llama3.1")
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from agent2.llm.openai import OpenAILLM
        return OpenAILLM(**kwargs)
    elif provider == "anthropic":
        from agent2.llm.anthropic import AnthropicLLM
        return AnthropicLLM(**kwargs)
    elif provider == "google":
        from agent2.llm.google import GoogleLLM
        return GoogleLLM(**kwargs)
    elif provider == "ollama":
        from agent2.llm.ollama import OllamaLLM
        return OllamaLLM(**kwargs)
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            f"Supported: openai, anthropic, google, ollama"
        )
