"""CLI entry point for agent2 command."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    """Launch TUI if agent2-tui is installed, otherwise fall back to chat CLI."""
    try:
        from agent2.app.tui import main as tui_main
        tui_main(argv)
    except ImportError:
        from agent2.app.chat import main as chat_main
        chat_main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
