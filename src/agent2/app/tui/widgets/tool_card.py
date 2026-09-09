"""Tool execution status card widget."""

from __future__ import annotations

from rich.table import Table
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Collapsible, Static
from textual.widgets._collapsible import CollapsibleTitle


class ToolTitle(CollapsibleTitle):
    """Collapsible title displaying the tool operation and a trailing status symbol."""

    DEFAULT_CSS = """
    ToolTitle {
        width: 100%;
        padding: 0;
        margin: 0;
        background: transparent;
    }
    """

    def __init__(
        self,
        label: str,
        *,
        running: bool = False,
        collapsed: bool = True,
        **kwargs,
    ) -> None:
        self.running = running
        super().__init__(
            label=label,
            collapsed_symbol=">",
            expanded_symbol="v",
            collapsed=collapsed,
            **kwargs,
        )

    async def _on_click(self, event: events.Click) -> None:
        if self.running:
            event.stop()
            return
        await super()._on_click(event)

    def action_toggle_collapsible(self) -> None:
        if self.running:
            return
        super().action_toggle_collapsible()

    def _update_label(self) -> None:
        if not hasattr(self, "running"):
            return
        sym = "⏳" if self.running else (self.collapsed_symbol if self.collapsed else self.expanded_symbol)
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True)
        grid.add_row(self.label, sym)
        self.update(grid)


class ToolCollapsible(Collapsible):
    """Collapsible container for tool execution output."""

    def __init__(
        self,
        *children: Widget,
        title: str = "Toggle",
        collapsed: bool = True,
        running: bool = False,
        is_error: bool = False,
        **kwargs,
    ) -> None:
        self.is_error = is_error
        super().__init__(*children, title=title, collapsed=collapsed, **kwargs)
        self._title = ToolTitle(title, running=running, collapsed=collapsed)

    def compose(self) -> ComposeResult:
        yield self._title
        if self.is_error:
            yield Static("[red]❌ Error[/red]", id="tool-status")
        with self.Contents():
            yield from self._contents_list


class ToolCard(Vertical):
    """Displays a tool invocation: name, arguments, spinner, and result."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict,  # type: ignore[type-arg]
        result: str | None = None,
        is_error: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._arguments = arguments
        self._initial_result = result
        self._initial_is_error = is_error

    def _get_operation_text(self) -> str:
        """Extract the formatted operation line."""
        args_display = ", ".join(
            f"{k}={_truncate(repr(v), 80)}" for k, v in self._arguments.items()
        )
        if args_display:
            return f"[bold yellow]⚙ {self._tool_name}[/bold yellow]  [dim]{args_display}[/dim]"
        return f"[bold yellow]⚙ {self._tool_name}[/bold yellow]"

    def _get_result_title(self) -> str:
        """Extract a descriptive result title showing the command's first line (backwards compatibility)."""
        cmd_line = ""
        for key in ("command", "cmd", "code", "script"):
            val = self._arguments.get(key)
            if isinstance(val, str) and val.strip():
                cmd_line = val.strip().splitlines()[0].strip()
                break

        if not cmd_line:
            for key in ("path", "query", "url", "filename", "pattern"):
                val = self._arguments.get(key)
                if val:
                    cmd_line = f"{self._tool_name} {val}".strip()
                    break

        if not cmd_line:
            args_str = " ".join(f"{k}={repr(v)}" for k, v in self._arguments.items())
            if args_str:
                cmd_line = f"{self._tool_name} {args_str}".strip().splitlines()[0].strip()
            else:
                cmd_line = self._tool_name

        if len(cmd_line) > 60:
            cmd_line = cmd_line[:57] + "…"

        return f"Result: {cmd_line}"

    def compose(self) -> ComposeResult:
        display = self._initial_result or ""
        if len(display) > 500:
            display = display[:500] + "\n… (truncated)"
        yield ToolCollapsible(
            Static(display, id="result-content"),
            title=self._get_operation_text(),
            collapsed=True,
            running=self._initial_result is None,
            is_error=self._initial_result is not None and self._initial_is_error,
            classes="tool-result",
        )

    def set_result(self, content: str, *, is_error: bool = False) -> None:
        """Update the card with the tool execution result."""
        self._initial_result = content
        self._initial_is_error = is_error

        collapsible = self.query_one(".tool-result", ToolCollapsible)
        collapsible.is_error = is_error
        title = collapsible.query_one(ToolTitle)
        title.running = False
        title._update_label()

        display = content if len(content) <= 500 else content[:500] + "\n… (truncated)"
        content_w = collapsible.query_one("#result-content", Static)
        content_w.update(display)

        status_widgets = collapsible.query("#tool-status")
        if is_error:
            if not status_widgets:
                contents = collapsible.query_one("Contents")
                collapsible.mount(Static("[red]❌ Error[/red]", id="tool-status"), before=contents)
            else:
                status_widgets.first().update("[red]❌ Error[/red]")
        else:
            for w in status_widgets:
                w.remove()


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"

