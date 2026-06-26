"""Ollama local model adapter (OpenAI-compatible API)."""

from __future__ import annotations

from typing import Any

from agent2.llm.openai import OpenAILLM


class OllamaLLM(OpenAILLM):
    """Adapter for Ollama local models.

    Ollama exposes an OpenAI-compatible API at ``/v1``, so this adapter
    simply reuses :class:`OpenAILLM` with a custom base URL and a
    dummy API key.

    Parameters
    ----------
    model : str
        Ollama model name, e.g. ``"llama3.1"``, ``"qwen2.5"``.
    base_url : str
        Ollama server URL. Defaults to ``http://localhost:11434/v1``.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        *,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        if base_url is None:
            from agent2.utils.config import settings
            base_url = settings.ollama_base_url.rstrip("/") + "/v1"

        super().__init__(
            model,
            api_key="ollama",  # Ollama doesn't need a real key
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
