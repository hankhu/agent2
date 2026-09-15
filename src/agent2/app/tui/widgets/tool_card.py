"""Tool execution status card widget."""

from __future__ import annotations

import time

from rich.markup import escape
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Collapsible, Static
from textual.widgets._collapsible import CollapsibleTitle


LONG_OPERATION_SECONDS = 5.0


def _fmt_duration(seconds: float) -> str:
    s = int(max(0.0, seconds))
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


def _fmt_clock(timestamp: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


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
        event.stop()
        event.prevent_default()
        if not self.running:
            self.post_message(self.Toggle())

    def action_toggle_collapsible(self) -> None:
        if self.running:
            return
        super().action_toggle_collapsible()

    def _update_label(self) -> None:
        if not hasattr(self, "running"):
            return
        sym = "⏳" if self.running else (self.collapsed_symbol if self.collapsed else self.expanded_symbol)
        self.update(f"{self.label}  {sym}")


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
        self._started_at = time.time()
        self._started_monotonic = time.monotonic()
        self._duration: float | None = None

    @property
    def duration(self) -> float | None:
        """Measured execution duration in seconds (``None`` until completed)."""
        return self._duration

    @property
    def started_at(self) -> float:
        """Wall-clock timestamp when the operation started."""
        return self._started_at

    def _get_operation_text(self) -> str:
        """Extract the formatted operation line."""
        # Friendly display for common tools
        friendly = self._friendly_operation()
        if friendly:
            return friendly

        args_display = ", ".join(
            f"{k}={_truncate(repr(v), 80)}" for k, v in self._arguments.items()
        )
        tool_name = escape(self._tool_name)
        if args_display:
            return f"[bold yellow]⚙ {tool_name}[/bold yellow]  [dim]{escape(args_display)}[/dim]"
        return f"[bold yellow]⚙ {tool_name}[/bold yellow]"

    def _friendly_operation(self) -> str | None:
        """Return a concise one-line label for well-known tools, or ``None``."""
        name = self._tool_name
        if name in ("file_read", "read_file"):
            path = self._arguments.get("path", "")
            return f"[bold yellow]⚙ /read:[/bold yellow] [dim]{escape(str(path))}[/dim]"
        if name in ("file_write", "write_file"):
            path = self._arguments.get("path", "")
            return f"[bold yellow]⚙ /write:[/bold yellow] [dim]{escape(str(path))}[/dim]"
        if name in ("shell_exec", "python_exec"):
            cmd = self._arguments.get("command") or self._arguments.get("code", "")
            first_line = str(cmd).strip().splitlines()[0] if cmd else ""
            return f"[bold yellow]⚙ /exec:[/bold yellow] [dim]{escape(first_line)}[/dim]"
        return None

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
            Static(display, id="result-content", markup=False),
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

        self._duration = max(0.0, time.monotonic() - self._started_monotonic)
        if self._duration >= LONG_OPERATION_SECONDS:
            duration_text = (
                f"{self._duration:.1f}s"
                if self._duration < 60
                else _fmt_duration(self._duration)
            )
            timing = (
                f"[dim]· {duration_text} "
                f"(started {_fmt_clock(self._started_at)})[/dim]"
            )
            title.label = f"{self._get_operation_text()}  {timing}"
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

