"""Configuration loader for agent2 apps.

Reads user-level config from ``~/.config/agent2/config.json`` and merges with
CLI arguments.  The config file is **optional** — sensible defaults are
used when it does not exist.

Example ``~/.config/agent2/config.json``::

    {
        "default": "gpt-4o-mini",
        "max_iterations": 50,
        "providers": {
            "openai": {
                "api_key": "sk-..."
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-..."
            },
            "ollama": {
                "base_url": "http://localhost:11434/v1"
            }
        },
        "models": {
            "gpt-4o-mini": { "provider": "openai" },
            "deepseek": { "provider": "deepseek", "model_id": "deepseek-chat" },
            "deepseek-r1": { "provider": "deepseek", "model_id": "deepseek-reasoner" },
            "llama3.1": { "provider": "ollama" }
        }
    }

Use :func:`load_models` to obtain a ``dict[str, OpenAILLM]``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ── Data Models ─────────────────────────────────────────────────────


class ProviderConfig(BaseModel):
    """Provider endpoint and credential definition."""

    base_url: str | None = Field(
        default=None,
        description="Custom base URL for OpenAI-compatible endpoint",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for the provider",
    )


class LLMConfig(BaseModel):
    """Backward-compatibility view for LLM parameters."""

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
    """Top-level application configuration.

    Eliminates redundancy by separating provider credentials (``providers``)
    from model aliases (``models``), with a concise top-level ``default`` model pointer.
    """

    default: str = Field(
        default="gpt-4o-mini",
        description="Default model alias or identifier",
    )
    temperature: float = Field(
        default=0.7,
        description="Default sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        description="Default maximum tokens for responses",
    )
    context_window: int | None = Field(
        default=None,
        description="Default context window size in tokens",
    )
    top_k: int | None = Field(
        default=None,
        description="Default top-k sampling parameter",
    )
    top_p: float | None = Field(
        default=None,
        description="Default top-p sampling parameter",
    )
    reasoning_effort: str | None = Field(
        default=None,
        description="Default reasoning effort (low, medium, high)",
    )
    pricing: dict[str, Any] | None = Field(
        default=None,
        description="Default pricing configuration",
    )
    max_iterations: int = Field(
        default=50,
        description="Default maximum iterations / turns for the agent reasoning loop",
    )
    providers: dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="Named provider endpoints and credentials (e.g. openai, deepseek, ollama)",
    )
    models: dict[str, Any] = Field(
        default_factory=dict,
        description="Named model definitions or aliases mapped to provider/model parameters",
    )
    rules: list[str] = Field(
        default_factory=list,
        description="Inline rules injected into the agent's system prompt",
    )
    mcp_servers: dict[str, Any] = Field(
        default_factory=dict,
        description="MCP server configurations keyed by server name",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_config(cls, data: Any) -> Any:
        """Migrate legacy ``llm`` section into ``default``, ``providers``, etc."""
        if not isinstance(data, dict):
            return data
        if "max_turns" in data and "max_iterations" not in data:
            data["max_iterations"] = data["max_turns"]
        if "max_rounds" in data and "max_iterations" not in data:
            data["max_iterations"] = data["max_rounds"]
        if "llm" in data and isinstance(data["llm"], dict):
            llm_obj = data["llm"]
            if "default" not in data and "model" in llm_obj:
                data["default"] = llm_obj["model"]
            if "temperature" not in data and "temperature" in llm_obj:
                data["temperature"] = llm_obj["temperature"]
            if "max_tokens" not in data and "max_tokens" in llm_obj:
                data["max_tokens"] = llm_obj["max_tokens"]
            if "providers" not in data:
                data["providers"] = {}
            if "default" not in data["providers"] and (llm_obj.get("base_url") or llm_obj.get("api_key")):
                data["providers"]["default"] = {
                    "base_url": llm_obj.get("base_url"),
                    "api_key": llm_obj.get("api_key"),
                }
        return data

    @property
    def llm(self) -> LLMConfig:
        """Backward-compatibility property returning default LLM parameters."""
        provider_name = "default" if "default" in self.providers else "openai"
        prov = self.providers.get(provider_name) or self.providers.get("openai")
        base_url = prov.base_url if prov else None
        api_key = prov.api_key if prov else None
        return LLMConfig(
            provider=provider_name,
            model=self.default,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def max_turns(self) -> int:
        """Alias for :attr:`max_iterations`."""
        return self.max_iterations

    def resolve_model(self, name_or_alias: str) -> dict[str, Any] | None:
        """Resolve a model name or alias with provider inheritance."""
        key = name_or_alias.strip()
        key_l = key.lower()

        # 1. Exact match in models
        entry = self.models.get(key) or self.models.get(key_l)

        # 2. Substring / fuzzy match in models
        if entry is None:
            best_entry: Any = None
            best_len = -1
            for cfg_key, cfg_val in self.models.items():
                cfg_key_l = cfg_key.lower()
                cfg_model_l = ""
                if isinstance(cfg_val, dict):
                    cfg_model_l = str(cfg_val.get("model_id") or cfg_val.get("model", "")).lower()
                elif isinstance(cfg_val, str):
                    cfg_model_l = cfg_val.lower()
                for candidate in (cfg_key_l, cfg_model_l):
                    if candidate and (candidate == key_l or candidate in key_l or key_l in candidate):
                        if len(candidate) > best_len:
                            best_len = len(candidate)
                            best_entry = cfg_val
            entry = best_entry

        # 3. Resolve matched model entry
        if entry is not None:
            if isinstance(entry, dict):
                res = dict(entry)
                provider_name = res.pop("provider", None)
                if provider_name and provider_name in self.providers:
                    p = self.providers[provider_name]
                    if p.base_url and "base_url" not in res:
                        res["base_url"] = p.base_url
                    if p.api_key and "api_key" not in res:
                        res["api_key"] = p.api_key
                model_id = res.pop("model_id", None) or res.pop("model", None) or key
                res["model"] = model_id
                if provider_name:
                    res["provider"] = provider_name
                if "temperature" not in res:
                    res["temperature"] = self.temperature
                if "max_tokens" not in res:
                    res["max_tokens"] = self.max_tokens
                if "context_window" not in res and self.context_window is not None:
                    res["context_window"] = self.context_window
                if "top_k" not in res and self.top_k is not None:
                    res["top_k"] = self.top_k
                if "top_p" not in res and self.top_p is not None:
                    res["top_p"] = self.top_p
                if "reasoning_effort" not in res and self.reasoning_effort is not None:
                    res["reasoning_effort"] = self.reasoning_effort
                if "pricing" not in res and self.pricing is not None:
                    res["pricing"] = self.pricing
                return res
            elif isinstance(entry, str):
                if entry in self.providers:
                    p = self.providers[entry]
                    return {
                        "model": key,
                        "provider": entry,
                        "base_url": p.base_url,
                        "api_key": p.api_key,
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                        "context_window": self.context_window,
                        "top_k": self.top_k,
                        "top_p": self.top_p,
                        "reasoning_effort": self.reasoning_effort,
                        "pricing": self.pricing,
                    }
                return {
                    "model": entry,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "context_window": self.context_window,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                    "reasoning_effort": self.reasoning_effort,
                    "pricing": self.pricing,
                }

        # 4. If name_or_alias matches a provider name directly
        if key_l in self.providers or key in self.providers:
            prov_entry = self.providers.get(key) or self.providers.get(key_l)
            if prov_entry is not None:
                return {
                    "model": key,
                    "provider": key,
                    "base_url": prov_entry.base_url,
                    "api_key": prov_entry.api_key,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "context_window": self.context_window,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                    "reasoning_effort": self.reasoning_effort,
                    "pricing": self.pricing,
                }

        return None


# ── Loader ──────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".config" / "agent2"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_BACKUP_FILE = CONFIG_DIR / "config.json.backup"
LAST_MODEL_FILE = CONFIG_DIR / "last_model"


def backup_config() -> bool:
    """Backup config.json to config.json.backup.

    Returns True if backup was created, False otherwise.
    """
    if not CONFIG_FILE.exists():
        return False
    try:
        CONFIG_BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(CONFIG_FILE, CONFIG_BACKUP_FILE)
        return True
    except OSError as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to backup %s to %s: %s", CONFIG_FILE, CONFIG_BACKUP_FILE, exc
        )
        return False


def get_system_editor() -> list[str]:
    """Return command arguments to launch the system editor."""
    import os
    import shlex
    import shutil
    import sys

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return shlex.split(editor)

    if sys.platform == "win32":
        return ["notepad"]

    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]

    if sys.platform == "darwin":
        return ["open", "-t"]

    return ["vi"]


def prepare_and_backup_config() -> tuple[bool, str]:
    """Ensure config.json exists, and backup to config.json.backup.

    Returns (backed_up: bool, path_str: str).
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        template = {
            "default": "gpt-4o-mini",
            "providers": {},
            "models": {},
        }
        try:
            CONFIG_FILE.write_text(
                json.dumps(template, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    backed_up = backup_config()
    return backed_up, str(CONFIG_FILE)


def validate_after_edit() -> tuple[bool, str]:
    """Validate config.json after editing; refresh backup if valid."""
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        AppConfig.model_validate(raw)
        backup_config()
        return (
            True,
            f"Configuration updated successfully (backed up to {CONFIG_BACKUP_FILE.name}).",
        )
    except Exception as exc:
        return (
            False,
            f"Error in {CONFIG_FILE.name}: {exc}. Fallback to {CONFIG_BACKUP_FILE.name}.",
        )


def get_last_model() -> str | None:
    """Return the last model selected by the user, if any."""
    try:
        if LAST_MODEL_FILE.exists():
            value = LAST_MODEL_FILE.read_text(encoding="utf-8").strip()
            return value or None
    except OSError:
        pass
    return None


def set_last_model(model: str) -> None:
    """Persist the last model selected by the user."""
    try:
        LAST_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_MODEL_FILE.write_text(model.strip(), encoding="utf-8")
    except OSError:
        pass


def load_config() -> AppConfig:
    """Load configuration from ``~/.config/agent2/config.json``.

    Catches exceptions when reading ``config.json`` and falls back to
    ``config.json.backup`` if available. Returns default :class:`AppConfig`
    when neither exists or both are invalid.
    """
    import logging

    _log = logging.getLogger(__name__)

    if not CONFIG_FILE.exists():
        if CONFIG_BACKUP_FILE.exists():
            try:
                raw = json.loads(CONFIG_BACKUP_FILE.read_text(encoding="utf-8"))
                return AppConfig.model_validate(raw)
            except Exception as exc:
                _log.warning(
                    "Failed to load backup config %s: %s", CONFIG_BACKUP_FILE, exc
                )
        return AppConfig()

    try:
        raw: dict[str, Any] = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except Exception as exc:
        _log.warning(
            "Error reading config from %s: %s. Using backup %s.",
            CONFIG_FILE,
            exc,
            CONFIG_BACKUP_FILE,
        )
        if CONFIG_BACKUP_FILE.exists():
            try:
                backup_raw: dict[str, Any] = json.loads(
                    CONFIG_BACKUP_FILE.read_text(encoding="utf-8")
                )
                return AppConfig.model_validate(backup_raw)
            except Exception as backup_exc:
                _log.warning(
                    "Error reading backup config from %s: %s. Using default config.",
                    CONFIG_BACKUP_FILE,
                    backup_exc,
                )
        return AppConfig()


def load_models() -> dict[str, Any]:
    """Instantiate LLMs from the ``models`` and ``providers`` sections.

    Returns
    -------
    dict[str, OpenAILLM]
        Mapping of model name → instantiated LLM instance.
    """
    import logging

    from agent2.llm import create_llm

    _log = logging.getLogger(__name__)
    config = load_config()
    instances: dict[str, Any] = {}

    for key in config.models:
        try:
            instances[key] = create_llm(key)
        except Exception as exc:
            _log.warning("Failed to load model '%s': %s", key, exc)

    for p_key in config.providers:
        if p_key not in instances:
            try:
                instances[p_key] = create_llm(p_key)
            except Exception as exc:
                _log.warning("Failed to load provider '%s': %s", p_key, exc)

    return instances


def update_mcp_server_disabled(server_name: str, disabled: bool) -> bool:
    """Update disabled status of an MCP server in ~/.config/agent2/config.json.

    Returns
    -------
    bool
        True if successfully updated and written, False otherwise.
    """
    raw: dict[str, Any] | None = None
    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if raw is None and CONFIG_BACKUP_FILE.exists():
        try:
            raw = json.loads(CONFIG_BACKUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if raw is None:
        return False
    mcp_servers = raw.get("mcp_servers")
    if not isinstance(mcp_servers, dict) or server_name not in mcp_servers:
        return False
    srv = mcp_servers[server_name]
    if isinstance(srv, dict):
        srv["disabled"] = disabled
    try:
        backup_config()
        CONFIG_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        backup_config()
        return True
    except OSError:
        return False

