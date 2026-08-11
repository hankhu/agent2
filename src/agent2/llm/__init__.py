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
        A built-in provider name (``"openai"``, ``"anthropic"``, ``"google"``,
        ``"ollama"``) **or** any key defined in the ``models`` dict of
        ``~/.config/agent2/config.json``.
    **kwargs
        Passed directly to the provider constructor.  When the provider is
        resolved from the config file these kwargs are merged on top of the
        config values (caller wins on conflicts).

    Returns
    -------
    BaseLLM
        A configured LLM instance.

    Examples
    --------
    >>> llm = create_llm("openai", model="gpt-4o")
    >>> llm = create_llm("anthropic", model="claude-sonnet-4-20250514")
    >>> llm = create_llm("ollama", model="llama3.1")
    >>> llm = create_llm("deepseek")  # resolved from config models dict
    """
    provider_key = provider.lower().strip()

    if provider_key == "openai":
        from agent2.llm.openai import OpenAILLM
        return OpenAILLM(**kwargs)
    elif provider_key == "anthropic":
        from agent2.llm.anthropic import AnthropicLLM
        return AnthropicLLM(**kwargs)
    elif provider_key == "google":
        from agent2.llm.google import GoogleLLM
        return GoogleLLM(**kwargs)
    elif provider_key == "ollama":
        from agent2.llm.ollama import OllamaLLM
        return OllamaLLM(**kwargs)
    else:
        # Fall back to the user config models dict.
        return _create_llm_from_config(provider_key, **kwargs)


def _create_llm_from_config(key: str, **kwargs: Any) -> BaseLLM:
    """Resolve *key* from ``~/.config/agent2/config.json`` ``models`` dict.

    The config entry supplies the base provider + kwargs; any extra *kwargs*
    passed here override the config values.
    """
    from agent2.app.config import KNOWN_PROVIDERS, load_config

    config = load_config()
    models = config.models

    if key not in models:
        raise ValueError(
            f"Unknown LLM provider: {key!r}. "
            f"Built-in providers: openai, anthropic, google, ollama. "
            f"Config-defined models: {sorted(models) or '(none)'}"
        )

    entry = models[key]
    if not isinstance(entry, dict):
        raise ValueError(
            f"models[{key!r}]: expected a dict of kwargs, got {type(entry).__name__!r}"
        )

    if key in KNOWN_PROVIDERS:
        # Key is itself the provider name.
        resolved_provider = key
        config_kwargs: dict[str, Any] = dict(entry)
    else:
        # Custom alias — must contain a "provider" field.
        config_kwargs = dict(entry)
        resolved_provider = config_kwargs.pop("provider", None)
        if resolved_provider is None:
            raise ValueError(
                f"models[{key!r}]: not a known provider and missing 'provider' field"
            )

    # Caller kwargs win over config values.
    merged = {**config_kwargs, **kwargs}
    return create_llm(resolved_provider, **merged)
