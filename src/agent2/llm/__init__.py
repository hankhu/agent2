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
        (``"openai"``, ``"ollama"``), or a key defined in the ``models`` dict
        of ``~/.config/agent2/config.json``.
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
        entry = config.models.get(name_or_model) or config.models.get(key)
        if entry is None:
            # Also match when the user adds a friendly prefix (e.g. "小米Mimo-v2.5"
            # should resolve to the configured "mimo-v2.5").
            best_entry: Any = None
            best_len = -1
            for cfg_key, cfg_entry in config.models.items():
                cfg_key_l = cfg_key.lower()
                if isinstance(cfg_entry, dict):
                    cfg_model_l = str(cfg_entry.get("model", "")).lower()
                else:
                    cfg_model_l = str(cfg_entry).lower()
                for candidate in (cfg_key_l, cfg_model_l):
                    if candidate and (candidate == key or candidate in key):
                        if len(candidate) > best_len:
                            best_len = len(candidate)
                            best_entry = cfg_entry
            entry = best_entry

        if entry is not None:
            if isinstance(entry, dict):
                config_kwargs = dict(entry)
                config_kwargs.pop("provider", None)
                merged = {**kwargs, **config_kwargs}
                return OpenAILLM(**merged)
            elif isinstance(entry, str):
                return OpenAILLM(model=entry, **kwargs)
    except Exception:
        pass

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
