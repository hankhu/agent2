"""Status bar widget — model, token usage, context window, and session time."""

from __future__ import annotations

import time

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


class StatusBar(Static):
    """Top-of-screen bar showing model, token usage, and processing state.

    Layout::

        Agent2 │ Model: gpt-4o  ⠋ Processing… (3s)  ↑in 1.2k (1%) ↓out 345 (0%)
        ctx 12.3k/128k (10%)  ⏱ 5m12s

    Input/output percentages are relative to the context window. While
    :attr:`busy` is ``True`` an animated spinner plus a status label
    (e.g. ``Processing…``) is shown until the response returns.
    """

    SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    mode: reactive[str] = reactive("AGENT")
    model_name: reactive[str] = reactive("—")
    busy: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("")

    # Token usage for the current conversation
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
        # Refresh once per second so the session timer stays current.
        self._clock_timer = self.set_interval(1.0, lambda: self.refresh())

    # ── Rendering ───────────────────────────────────────────────

    def _pct(self, n: int) -> str:
        """Percent suffix relative to the context window, e.g. `` (12%)``."""
        if not self.context_window:
            return ""
        return f" ({round(n * 100 / self.context_window)}%)"

    def render(self) -> str:
        mode_upper = self.mode.upper()
        if mode_upper == "PLAN":
            mode_badge = "[bold yellow]PLAN[/bold yellow]"
        elif mode_upper == "ASK":
            mode_badge = "[bold cyan]ASK[/bold cyan]"
        else:
            mode_badge = "[bold green]AGENT[/bold green]"

        parts = [f"Agent2 \\[{mode_badge}] │ Model: {self.model_name}"]

        if self.busy:
            frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
            elapsed = ""
            if self._busy_since is not None:
                elapsed = f" ({time.monotonic() - self._busy_since:.0f}s)"
            label = self.status_text or "Processing…"
            parts.append(f"[cyan]{frame}[/cyan] {label}{elapsed}")

        # Token usage: cumulative in/out (with % of the window) +
        # current context size vs window
        if self.input_tokens or self.output_tokens:
            parts.append(
                f"[green]↑{_fmt_tokens(self.input_tokens)}{self._pct(self.input_tokens)}[/green] "
                f"[blue]↓{_fmt_tokens(self.output_tokens)}{self._pct(self.output_tokens)}[/blue]"
            )
        if self.context_window:
            pct = self.context_tokens * 100 / self.context_window
            color = (
                "red" if pct >= 90
                else "yellow" if pct >= 75
                else "green"
            )
            parts.append(
                f"ctx {_fmt_tokens(self.context_tokens)}/{_fmt_tokens(self.context_window)} "
                f"[{color}]({pct:.0f}%)[/{color}]"
            )

        # Session duration
        parts.append(f"⏱ {_fmt_duration(time.monotonic() - self._session_start)}")

        return "  ".join(parts)

    # ── Spinner (busy animation) ────────────────────────────────

    def reset_timer(self) -> None:
        """Restart the conversation-duration clock (new / resumed conversation)."""
        self._session_start = time.monotonic()

    def watch_busy(self, busy: bool) -> None:
        """Start/stop the spinner animation when the busy state changes."""
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
