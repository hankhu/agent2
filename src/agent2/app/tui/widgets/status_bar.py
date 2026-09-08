"""Status bar and context bar widgets for modern TUI layout."""

from __future__ import annotations

import os
from pathlib import Path
import time

from rich.table import Table
from textual.reactive import reactive
from textual.widgets import Static


def _fmt_tokens(n: int) -> str:
    """Compact token count: 1234 → 1.2k, 1234567 → 1.2M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_duration(seconds: float) -> str:
    """Format a duration as ``1h23m`` / ``12m34s`` / ``45s``."""
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


class ContextBar(Static):
    """Context bar situated directly above the chat input box.

    Displays:
      - Left: Current working directory (or active tool/spinner if busy)
      - Right: Session token usage, context ratio, and active model
    """

    SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    cwd: reactive[str] = reactive("")
    model_name: reactive[str] = reactive("—")
    provider: reactive[str] = reactive("")
    busy: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("")

    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    context_tokens: reactive[int] = reactive(0)
    context_window: reactive[int] = reactive(0)

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._frame = 0
        self._busy_since: float | None = None
        self._spinner_timer = None
        self._session_start = time.monotonic()
        self._clock_timer = None

    def on_mount(self) -> None:
        self._clock_timer = self.set_interval(1.0, lambda: self.refresh())
        if not self.cwd:
            self.cwd = os.getcwd()

    def reset_timer(self) -> None:
        self._session_start = time.monotonic()

    def watch_busy(self, busy: bool) -> None:
        if busy:
            self._busy_since = time.monotonic()
            if self._spinner_timer is None:
                self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
        else:
            self._busy_since = None
            if self._spinner_timer is not None:
                self._spinner_timer.stop()
                self._spinner_timer = None
            self._frame = 0

    def _tick_spinner(self) -> None:
        self._frame += 1
        self.refresh()

    def render(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", no_wrap=True)
        grid.add_column(justify="right", no_wrap=True)

        # Left side: Path or spinner
        if self.busy:
            frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
            elapsed = ""
            if self._busy_since is not None:
                elapsed = f" ({time.monotonic() - self._busy_since:.0f}s)"
            label = self.status_text or "Processing…"
            left = f"[cyan]{frame}[/cyan] [bold]{label}[/bold]{elapsed}"
        else:
            p = self.cwd or os.getcwd()
            left = f"[dim]{p}[/dim]"

        # Right side: Session token usage and context
        right_items = []
        total_tokens = self.input_tokens + self.output_tokens
        if total_tokens > 0:
            right_items.append(f"Session: [bold]{_fmt_tokens(total_tokens)}[/bold] tokens")
        else:
            right_items.append("Session: 0 tokens")

        if self.context_window and self.context_tokens:
            pct = self.context_tokens * 100 / self.context_window
            color = "red" if pct >= 90 else "yellow" if pct >= 75 else "green"
            right_items.append(f"ctx {_fmt_tokens(self.context_tokens)}/{_fmt_tokens(self.context_window)} [{color}]({pct:.0f}%)[/{color}]")

        if self.model_name and self.model_name != "—":
            if self.provider:
                right_items.append(f"[dim]\\[{self.provider}] {self.model_name}[/dim]")
            else:
                right_items.append(f"[dim]{self.model_name}[/dim]")

        right = "  ".join(right_items)
        grid.add_row(left, right)
        return grid


class StatusBar(Static):
    """Bottom footer bar showing navigation hints and interaction mode."""

    SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    mode: reactive[str] = reactive("AGENT")
    model_name: reactive[str] = reactive("—")
    provider: reactive[str] = reactive("")
    busy: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("")

    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    context_tokens: reactive[int] = reactive(0)
    context_window: reactive[int] = reactive(0)

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._frame = 0
        self._busy_since: float | None = None
        self._spinner_timer = None
        self._session_start = time.monotonic()
        self._clock_timer = None

    def on_mount(self) -> None:
        self._clock_timer = self.set_interval(1.0, lambda: self.refresh())

    def reset_timer(self) -> None:
        self._session_start = time.monotonic()

    def watch_busy(self, busy: bool) -> None:
        if busy:
            self._busy_since = time.monotonic()
            if self._spinner_timer is None:
                self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
        else:
            self._busy_since = None
            if self._spinner_timer is not None:
                self._spinner_timer.stop()
                self._spinner_timer = None
            self._frame = 0

    def _tick_spinner(self) -> None:
        self._frame += 1
        self.refresh()

    def render(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", no_wrap=True)
        grid.add_column(justify="right", no_wrap=True)

        left = "[dim]+ sessions  ·  / commands  ·  ? help  ·  tab switch[/dim]"

        mode_upper = self.mode.upper()
        if mode_upper == "PLAN":
            mode_badge = "[bold yellow]PLAN[/bold yellow]"
        elif mode_upper == "ASK":
            mode_badge = "[bold cyan]ASK[/bold cyan]"
        else:
            mode_badge = "[bold green]AGENT[/bold green]"

        grid.add_row(left, mode_badge)
        return grid


FooterBar = StatusBar
