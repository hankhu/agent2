"""Configuration loader for agent2 apps.

Reads user-level config from ``~/.agent2/config.json`` and merges with
CLI arguments.  The config file is **optional** — sensible defaults are
used when it does not exist.

Example ``~/.config/agent2.json``::

    {
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 4096,
            "api_key": null,
            "base_url": null
        }
    }
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
        description="LLM provider: openai | anthropic | google | ollama",
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Model identifier for the chosen provider",
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
        description="API key (provider-specific)",
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL for the API endpoint",
    )


class AppConfig(BaseModel):
    """Top-level application configuration."""

    llm: LLMConfig = Field(default_factory=LLMConfig)


# ── Loader ──────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config"
CONFIG_FILE = CONFIG_DIR / "agent2.json"


def load_config() -> AppConfig:
    """Load configuration from ``~/.agent2/config.json``.

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
