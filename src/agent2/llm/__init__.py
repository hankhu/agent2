"""LLM abstraction layer — OpenAI-compatible interface for all models.

Quick start::

    from agent2.llm import create_llm, Message

    llm = create_llm(model="gpt-4o-mini")
    response = await llm.chat([Message.user("Hello!")])
    print(response.content)
"""

from __future__ import annotations

from typing import Any

from agent2.llm.base import BaseLLM
from agent2.llm.openai import OpenAILLM
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
    "OpenAILLM",
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


def create_llm(name_or_model: str = "openai", **kwargs: Any) -> OpenAILLM:
    """Factory function to create an OpenAI-compatible LLM instance.

    Parameters
    ----------
    name_or_model : str
        A model name (e.g. ``"gpt-4o"``, ``"deepseek-chat"``), a preset name
        (``"openai"``, ``"ollama"``), or a key defined in the ``models`` or ``providers``
        dict of ``~/.config/agent2/config.json``.
    **kwargs
        Passed directly to :class:`OpenAILLM` (e.g. ``model``, ``api_key``,
        ``base_url``, ``temperature``, ``max_tokens``). Caller kwargs override
        config values.

    Returns
    -------
    OpenAILLM
        A configured LLM instance.
    """
    key = name_or_model.lower().strip()

    # 1. Check user config file (~/.config/agent2/config.json)
    try:
        from agent2.app.config import load_config

        config = load_config()
        resolved = config.resolve_model(name_or_model)
        if resolved:
            merged = {**resolved, **kwargs}
            return OpenAILLM(**merged)
    except (ImportError, FileNotFoundError, KeyError) as exc:
        import logging
        logging.getLogger(__name__).debug("Config-based LLM creation skipped: %s", exc)

    # 2. Built-in presets
    if key in ("openai", "default"):
        return OpenAILLM(**kwargs)
    elif key == "ollama":
        defaults: dict[str, Any] = {
            "model": "llama3.1",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
        }
        return OpenAILLM(**{**defaults, **kwargs})

    # 3. Direct model name
    if "model" not in kwargs:
        kwargs["model"] = name_or_model
    return OpenAILLM(**kwargs)

