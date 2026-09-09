"""Welcome banner widget showing Mascot, version, and tips."""

from __future__ import annotations

import random
from textual.widgets import Static

from agent2 import __version__

TIPS: list[tuple[str, str]] = [
    ("/plan", "Analyze intent, break down tasks, confirm and execute"),
    ("/ask", "Read-only mode with tool execution and write disabled"),
    ("/agent", "Default autonomous agent mode with full tool capabilities"),
    ("/model", "Switch the active language model dynamically"),
    ("/sessions", "Manage, resume, rename, or delete conversation sessions"),
    ("#file <path>", "Inject file content directly into conversation context"),
    ("#dir <path>", "Inject directory listings directly into context"),
]


class WelcomeBanner(Static):
    """Initial greeting banner with Mascot and rotating tips."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 1 2 1 2;
        margin: 0;
        background: transparent;
    }
    """

    def __init__(self, *args, tip: tuple[str, str] | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.tip = tip or random.choice(TIPS)

    def render(self) -> str:
        cmd, desc = self.tip
        return (
            f" [bright_cyan]┌─┐[/bright_cyan]\n"
            f" [bright_cyan]│[/bright_cyan] [magenta]\"[/magenta] [bright_cyan]│[/bright_cyan]  [bold]Agent2 v{__version__}[/bold] is ready to assist.\n"
            f" [magenta] ▀▀[/magenta]   [dim]Verify outputs for correctness.[/dim]\n\n"
            f" [dodger_blue1]• Tip:[/dodger_blue1] [bold]{cmd}[/bold]\n"
            f"   [dim]└ {desc}[/dim]"
        )
