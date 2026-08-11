"""Configuration loader for agent2 apps.

Reads user-level config from ``~/.config/agent2/config.json`` and merges with
CLI arguments.  The config file is **optional** — sensible defaults are
used when it does not exist.

Example ``~/.config/agent2/config.json``::

    {
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 4096,
            "api_key": null,
            "base_url": null
        },
        "models": {
            "openai": {"model": "gpt-4o-mini"},
            "my-claude": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
        }
    }

The ``models`` field is a dict where each entry maps a *key* to LLM kwargs:

* If the key is a **known provider** (``openai``, ``anthropic``, ``google``,
  ``ollama``), the value dict is passed directly as kwargs to
  :func:`~agent2.llm.create_llm` with that provider.
* Otherwise the value dict **must** contain a ``"provider"`` field; the
  remaining fields become kwargs.

Use :func:`load_models` to obtain a ``dict[str, BaseLLM]``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ── Known providers ──────────────────────────────────────────────────

KNOWN_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "google", "ollama"})

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
    models: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Named model definitions. Each key maps to a dict of kwargs for "
            "create_llm. If the key is a known provider name the dict is used "
            "directly; otherwise a 'provider' field must be present inside the dict."
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

    Each entry in ``config.models`` is resolved as follows:

    * **Known provider key** (``openai`` / ``anthropic`` / ``google`` /
      ``ollama``): the value dict is forwarded verbatim as kwargs to
      :func:`~agent2.llm.create_llm`.
    * **Custom key**: the value dict must contain a ``"provider"`` field
      that identifies the provider; all other fields become kwargs.

    Returns
    -------
    dict[str, BaseLLM]
        Mapping of model name → instantiated :class:`~agent2.llm.BaseLLM`.

    Raises
    ------
    ValueError
        If a custom-key entry is missing the ``"provider"`` field, or if
        the provider is unknown.
    """
    from agent2.llm import create_llm

    config = load_config()
    instances: dict[str, Any] = {}

    for key, value in config.models.items():
        if not isinstance(value, dict):
            raise ValueError(
                f"models[{key!r}]: expected a dict of kwargs, got {type(value).__name__!r}"
            )

        key_lower = key.lower().strip()
        if key_lower in KNOWN_PROVIDERS:
            # Key itself is the provider name — use value as kwargs directly.
            provider = key_lower
            kwargs = dict(value)
        else:
            # Custom alias — must contain a "provider" field.
            kwargs = dict(value)
            provider = kwargs.pop("provider", None)
            if provider is None:
                raise ValueError(
                    f"models[{key!r}]: not a known provider and missing 'provider' field"
                )

        instances[key] = create_llm(provider, **kwargs)

    return instances
