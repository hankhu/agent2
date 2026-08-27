"""Status bar widget — model name and token usage."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Top-of-screen bar showing active model and cumulative token count."""

    model_name: reactive[str] = reactive("—")
    token_count: reactive[int] = reactive(0)

    def render(self) -> str:  # type: ignore[override]
        tokens = f"Tokens: {self.token_count:,}" if self.token_count else ""
        return f" Agent2 │ Model: {self.model_name}  {tokens}"
