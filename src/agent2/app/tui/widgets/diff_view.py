"""Unified Diff preview widget with red/green syntax highlighting."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static
from textual.containers import Vertical


class DiffView(Vertical):
    """Render a unified diff with colour-coded lines."""

    def __init__(self, diff_text: str, filename: str = "") -> None:
        super().__init__()
        self._diff_text = diff_text
        self._filename = filename

    def compose(self):  # type: ignore[override]
        if self._filename:
            yield Static(f"[bold blue]📝 {self._filename}[/bold blue]")
        yield Static(self._colorize())

    # ── internal ────────────────────────────────────────────────

    def _colorize(self) -> Text:
        text = Text()
        for line in self._diff_text.splitlines(keepends=True):
            stripped = line.rstrip("\n")
            if stripped.startswith("+++") or stripped.startswith("---"):
                text.append(stripped + "\n", style="bold blue")
            elif stripped.startswith("@@"):
                text.append(stripped + "\n", style="cyan")
            elif stripped.startswith("+"):
                text.append(stripped + "\n", style="green")
            elif stripped.startswith("-"):
                text.append(stripped + "\n", style="red")
            else:
                text.append(stripped + "\n")
        return text
