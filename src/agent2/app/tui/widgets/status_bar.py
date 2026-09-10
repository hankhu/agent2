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
    s = int(max(0.0, seconds))
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


def _fmt_clock(timestamp: float) -> str:
    """Format a wall-clock timestamp as ``HH:MM:SS``."""
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def _fmt_operation_duration(seconds: float) -> str:
    """Format an operation duration with sub-minute precision."""
    if seconds < 60:
        return f"{max(0.0, seconds):.1f}s"
    return _fmt_duration(seconds)


def _fmt_tps(tps: float) -> str:
    """Format a tokens-per-second value compactly."""
    if tps >= 100:
        return f"{tps:.0f}"
    if tps >= 10:
        return f"{tps:.1f}"
    return f"{tps:.2f}"


# Operations slower than this are highlighted with their duration and start time.
LONG_OPERATION_SECONDS = 5.0


class ContextBar(Static):
    """Context bar situated directly above the chat input box.

    Displays:
      - Left: Current working directory (or active tool/spinner if busy)
      - Right: Session duration, token usage, TPS, context ratio, and active model
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
    cost: reactive[float] = reactive(0.0)
    tps: reactive[float] = reactive(0.0)
    long_operation: reactive[str] = reactive("")

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._frame = 0
        self._busy_since: float | None = None
        self._busy_started_at: float | None = None
        self._spinner_timer = None
        self._session_start = time.monotonic()
        self._clock_timer = None

    def on_mount(self) -> None:
        self._clock_timer = self.set_interval(1.0, lambda: self.refresh())
        if not self.cwd:
            self.cwd = os.getcwd()

    def reset_timer(self) -> None:
        self._session_start = time.monotonic()

    @property
    def session_duration(self) -> float:
        """Current session wall-clock duration in seconds."""
        return max(0.0, time.monotonic() - self._session_start)

    @session_duration.setter
    def session_duration(self, seconds: float) -> None:
        self._session_start = time.monotonic() - max(0.0, float(seconds))

    @property
    def last_operation(self) -> str:
        """Alias for :attr:`long_operation`."""
        return self.long_operation

    @last_operation.setter
    def last_operation(self, value: str) -> None:
        self.long_operation = value

    def watch_busy(self, busy: bool) -> None:
        if busy:
            self._busy_since = time.monotonic()
            self._busy_started_at = time.time()
            if self._spinner_timer is None:
                self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
        else:
            self._busy_since = None
            self._busy_started_at = None
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
                elapsed_seconds = max(0.0, time.monotonic() - self._busy_since)
                elapsed = f" ({_fmt_operation_duration(elapsed_seconds)}"
                if (
                    elapsed_seconds >= LONG_OPERATION_SECONDS
                    and self._busy_started_at is not None
                ):
                    elapsed += f", started {_fmt_clock(self._busy_started_at)}"
                elapsed += ")"
            label = self.status_text or "Processing…"
            left = f"[cyan]{frame}[/cyan] [bold]{label}[/bold]{elapsed}"
        else:
            p = self.cwd or os.getcwd()
            left = f"[dim]{p}[/dim]"

        # Right side: Slow-operation info, session duration, token usage, TPS, and context
        right_items = []
        if self.long_operation:
            right_items.append(f"[cyan]↳[/cyan] {self.long_operation}")
        session_elapsed = max(0.0, time.monotonic() - self._session_start)
        total_tokens = self.input_tokens + self.output_tokens
        cost_str = f" (${self.cost:.4f})" if self.cost > 0 else ""
        if total_tokens > 0:
            right_items.append(
                f"Session: [bold]{_fmt_tokens(total_tokens)}[/bold] tokens{cost_str} "
                f"[dim](⏱ {_fmt_duration(session_elapsed)})[/dim]"
            )
        else:
            right_items.append(
                f"Session: 0 tokens{cost_str} "
                f"[dim](⏱ {_fmt_duration(session_elapsed)})[/dim]"
            )
        if self.tps > 0:
            right_items.append(f"[dim]TPS:[/dim] [bold]{_fmt_tps(self.tps)}[/bold] [dim]tok/s[/dim]")

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

    active_tab: reactive[str] = reactive("current")
    mode: reactive[str] = reactive("AGENT")
    yolo: reactive[bool] = reactive(False)
    allow_all: reactive[bool] = reactive(False)
    model_name: reactive[str] = reactive("—")
    provider: reactive[str] = reactive("")
    busy: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("")

    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    context_tokens: reactive[int] = reactive(0)
    context_window: reactive[int] = reactive(0)
    cost: reactive[float] = reactive(0.0)
    tps: reactive[float] = reactive(0.0)
    long_operation: reactive[str] = reactive("")

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

    @property
    def session_duration(self) -> float:
        """Current session wall-clock duration in seconds."""
        return max(0.0, time.monotonic() - self._session_start)

    @session_duration.setter
    def session_duration(self, seconds: float) -> None:
        self._session_start = time.monotonic() - max(0.0, float(seconds))

    @property
    def last_operation(self) -> str:
        """Alias for :attr:`long_operation`."""
        return self.long_operation

    @last_operation.setter
    def last_operation(self, value: str) -> None:
        self.long_operation = value

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

        if self.active_tab == "sessions":
            left = (
                "[dim]↑/↓ select  ·  enter resume  ·  ctrl+x, x delete  ·  "
                "e/r rename  ·  tab next  ·  esc close[/dim]"
            )
        elif self.active_tab == "skills":
            left = "[dim]↑/↓ select  ·  enter invoke  ·  r reload  ·  tab next  ·  esc close[/dim]"
        else:
            left = (
                "[dim]? shortcuts  ·  + sessions  ·  / commands  ·  tab switch  ·  "
                "ctrl+c interrupt  ·  ctrl+o results  ·  ctrl+d quit  ·  esc[/dim]"
            )

        mode_upper = self.mode.upper()
        if mode_upper == "PLAN":
            mode_badge = "[bold yellow]PLAN[/bold yellow]"
        elif mode_upper == "ASK":
            mode_badge = "[bold cyan]ASK[/bold cyan]"
        else:
            mode_badge = "[bold green]AGENT[/bold green]"

        badges = [mode_badge]
        session_elapsed = max(0.0, time.monotonic() - self._session_start)
        if self.long_operation:
            badges.append(f"[dim]↳ {self.long_operation}[/dim]")
        badges.append(f"[dim]session: {_fmt_duration(session_elapsed)}[/dim]")
        if self.tps > 0:
            badges.append(f"[dim]TPS:[/dim] [bold]{_fmt_tps(self.tps)}[/bold] [dim]tok/s[/dim]")
        if self.yolo:
            badges.append("[bold red]YOLO[/bold red]")
        elif self.allow_all:
            badges.append("[bold magenta]ALLOW-ALL[/bold magenta]")

        grid.add_row(left, "  ".join(badges))
        return grid


FooterBar = StatusBar
