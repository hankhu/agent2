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
from agent2.llm.pricing import ModelPricing, guess_pricing

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
    "ModelPricing",
    "guess_pricing",
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
    cfg = None
    try:
        from agent2.app.config import load_config
        cfg = load_config()
    except Exception:
        pass

    global_extras: dict[str, Any] = {}
    if cfg is not None:
        if cfg.context_window is not None:
            global_extras["context_window"] = cfg.context_window
        if cfg.top_k is not None:
            global_extras["top_k"] = cfg.top_k
        if cfg.top_p is not None:
            global_extras["top_p"] = cfg.top_p
        if cfg.reasoning_effort is not None:
            global_extras["reasoning_effort"] = cfg.reasoning_effort
        if cfg.pricing is not None:
            global_extras["pricing"] = cfg.pricing
        if cfg.temperature is not None:
            global_extras["temperature"] = cfg.temperature

    if key in ("openai", "default"):
        defaults: dict[str, Any] = {"provider": "openai", **global_extras}
        if cfg and cfg.llm.base_url and "base_url" not in kwargs:
            defaults["base_url"] = cfg.llm.base_url
        if cfg and cfg.llm.provider and "provider" not in kwargs:
            defaults["provider"] = cfg.llm.provider
        return OpenAILLM(**{**defaults, **kwargs})
    elif key == "ollama":
        defaults = {
            "model": "llama3.1",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "provider": "ollama",
            **global_extras,
        }
        return OpenAILLM(**{**defaults, **kwargs})
    elif key == "deepseek":
        defaults = {
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "provider": "deepseek",
            **global_extras,
        }
        return OpenAILLM(**{**defaults, **kwargs})

    # 3. Direct model name
    direct_args: dict[str, Any] = {"model": name_or_model, **global_extras}
    if cfg:
        if cfg.llm.base_url and "base_url" not in kwargs:
            direct_args["base_url"] = cfg.llm.base_url
        if cfg.llm.provider and "provider" not in kwargs:
            direct_args["provider"] = cfg.llm.provider
    direct_args.update(kwargs)
    return OpenAILLM(**direct_args)

