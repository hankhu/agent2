"""Inline shortcut help panel displayed directly above the chat input."""

from __future__ import annotations

from textual.widgets import Static


SHORTCUT_HELP_TEXT = """\
[bold cyan]Keyboard shortcuts[/bold cyan]
[green]Enter[/green] send  ·  [green]Shift+Enter[/green] newline
[green]Tab[/green] next  ·  [green]Shift+Tab[/green] previous
[green]?[/green] shortcuts  ·  [green]+[/green] sessions  ·  [green]/[/green] commands
[green]Esc[/green] close/cancel  ·  [green]Ctrl+C[/green] interrupt
[green]Ctrl+O[/green] results  ·  [green]Ctrl+D[/green] quit

[bold cyan]Sessions panel[/bold cyan]
↑/↓ select  ·  Enter resume  ·  e/r rename
Ctrl+X, X delete

[bold cyan]Skills panel[/bold cyan]
↑/↓ select  ·  Enter invoke  ·  r reload"""


class ShortcutHelp(Static):
    """A compact, always-available list of keybindings shown above the input."""

    DEFAULT_CSS = """
    ShortcutHelp {
        display: none;
        height: auto;
        max-height: 14;
        overflow-y: auto;
        background: $surface;
        color: $text-muted;
        border: none;
        padding: 0 1;
        margin: 0;
    }

    ShortcutHelp.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        kwargs.setdefault("id", "shortcut-help")
        super().__init__(SHORTCUT_HELP_TEXT, **kwargs)

    @property
    def visible(self) -> bool:
        return self.has_class("visible")

    def show_help(self) -> None:
        self.add_class("visible")

    def hide_help(self) -> None:
        self.remove_class("visible")

    def toggle_help(self) -> bool:
        if self.visible:
            self.hide_help()
            return False
        self.show_help()
        return True
