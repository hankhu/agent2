"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Global configuration for the Agent2 framework.

    Values are loaded from environment variables with the AGENT2_ prefix.
    For example, AGENT2_DEFAULT_LLM_PROVIDER=openai
    """

    model_config = {"env_prefix": "AGENT2_"}

    # ── LLM Defaults ────────────────────────────────────────────────
    default_llm_provider: str = Field(
        default="openai",
        description="Default LLM provider: openai | anthropic | google | ollama",
    )
    default_model: str = Field(
        default="gpt-4o-mini",
        description="Default model name for the chosen provider",
    )
    default_temperature: float = Field(
        default=0.7,
        description="Default sampling temperature",
    )
    default_max_tokens: int = Field(
        default=4096,
        description="Default max tokens for LLM responses",
    )

    # ── API Keys ────────────────────────────────────────────────────
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    ollama_base_url: str = Field(default="http://localhost:11434")

    # ── Agent Defaults ──────────────────────────────────────────────
    agent_max_iterations: int = Field(
        default=10,
        description="Maximum iterations for the agent reasoning loop",
    )
    agent_verbose: bool = Field(
        default=True,
        description="Enable detailed Thought/Action/Observation logging",
    )

    # ── Memory ──────────────────────────────────────────────────────
    memory_max_messages: int = Field(
        default=50,
        description="Max messages in working memory before summarization",
    )


# Singleton instance — import this directly
settings = Settings()
