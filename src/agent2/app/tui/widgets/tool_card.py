"""Tool execution status card widget."""

from __future__ import annotations

from textual.widgets import Collapsible, Static
from textual.containers import Vertical


class ToolCard(Vertical):
    """Displays a tool invocation: name, arguments, spinner, and result."""

    def __init__(self, tool_name: str, arguments: dict) -> None:  # type: ignore[type-arg]
        super().__init__()
        self._tool_name = tool_name
        self._arguments = arguments

    def compose(self):  # type: ignore[override]
        args_display = ", ".join(
            f"{k}={_truncate(repr(v), 80)}" for k, v in self._arguments.items()
        )
        yield Static(f"[bold yellow]⚙ {self._tool_name}[/bold yellow]  [dim]{args_display}[/dim]")
        yield Static("⏳ Running…", id="tool-status")

    def set_result(self, content: str, *, is_error: bool = False) -> None:
        """Update the card with the tool execution result."""
        status = self.query_one("#tool-status", Static)
        if is_error:
            status.update("[red]❌ Error[/red]")
        else:
            status.update("[green]✓ Success[/green]")

        display = content if len(content) <= 500 else content[:500] + "\n… (truncated)"
        collapsed = len(content) > 200
        result = Collapsible(
            Static(display),
            title="Result",
            collapsed=collapsed,
            classes="tool-result",
        )
        self.mount(result)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
