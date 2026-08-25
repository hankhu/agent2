"""Configuration loader for agent2 apps.

Reads user-level config from ``~/.config/agent2/config.json`` and merges with
CLI arguments.  The config file is **optional** — sensible defaults are
used when it does not exist.

Example ``~/.config/agent2/config.json``::

    {
        "llm": {
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 4096,
            "api_key": null,
            "base_url": null
        },
        "models": {
            "deepseek": {
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-..."
            },
            "local": {
                "model": "llama3.1",
                "base_url": "http://localhost:11434/v1"
            }
        }
    }

Use :func:`load_models` to obtain a ``dict[str, OpenAILLM]``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ── Data Models ─────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    """LLM-related parameters stored in config.json."""

    provider: str = Field(
        default="openai",
        description="LLM provider (OpenAI-compatible)",
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Model identifier",
    )
    temperature: float = Field(
        default=0.7,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens for LLM responses",
    )
    api_key: str | None = Field(
        default=None,
        description="API key",
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL for OpenAI-compatible endpoint",
    )


class AppConfig(BaseModel):
    """Top-level application configuration."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    models: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Named model definitions. Each key maps to a dict of kwargs for create_llm "
            "or a model name string."
        ),
    )


# ── Loader ──────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config" / "agent2"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> AppConfig:
    """Load configuration from ``~/.config/agent2/config.json``.

    Returns a default :class:`AppConfig` when the file does not exist or
    is invalid JSON.
    """
    if not CONFIG_FILE.exists():
        return AppConfig()

    try:
        raw: dict[str, Any] = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except (json.JSONDecodeError, Exception):
        return AppConfig()


def load_models() -> dict[str, Any]:
    """Instantiate LLMs from the ``models`` section of the config file.

    Returns
    -------
    dict[str, OpenAILLM]
        Mapping of model name → instantiated LLM instance.
    """
    from agent2.llm import create_llm

    config = load_config()
    instances: dict[str, Any] = {}

    for key, value in config.models.items():
        if isinstance(value, dict):
            kwargs = dict(value)
            kwargs.pop("provider", None)
            instances[key] = create_llm(key, **kwargs)
        elif isinstance(value, str):
            instances[key] = create_llm(model=value)
        else:
            raise ValueError(
                f"models[{key!r}]: expected a dict or model string, got {type(value).__name__!r}"
            )

    return instances
