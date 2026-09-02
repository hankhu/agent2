"""HITL inline confirmation card for tool execution approval."""

from __future__ import annotations

from collections.abc import Callable
import difflib
from pathlib import Path

from textual import events
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from agent2.app.tui.widgets.diff_view import DiffView


class ConfirmCard(Vertical):
    """Inline confirmation card embedded within the message history stream."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict,  # type: ignore[type-arg]
        on_decision: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._arguments = arguments
        self.on_decision = on_decision
        self._decision: str | None = None

    def compose(self):  # type: ignore[override]
        args_display = " ".join(
            f"[dim]{k}=[/dim][cyan]{_truncate(repr(v), 120)}[/cyan]"
            for k, v in self._arguments.items()
        )
        if args_display:
            yield Static(
                f"[bold yellow]⚠ Approval Required:[/bold yellow] "
                f"[bold cyan]{self._tool_name}[/bold cyan]  {args_display}"
            )
        else:
            yield Static(
                f"[bold yellow]⚠ Approval Required:[/bold yellow] "
                f"[bold cyan]{self._tool_name}[/bold cyan]"
            )

        # Show inline diff for file_write
        diff = self._compute_diff()
        if diff:
            yield DiffView(diff, filename=str(self._arguments.get("path", "")))

        with Horizontal(id="confirm-buttons"):
            yield Button("[green][y] Approve[/green]", id="approve")
            yield Button("[red][n] Reject[/red]", id="reject")
            yield Button("[yellow][a] Always Allow[/yellow]", id="always")

    def on_mount(self) -> None:
        try:
            self.query_one("#approve", Button).focus()
        except Exception:
            pass

    # ── focus navigation & shortcuts ────────────────────────────

    def _focus_relative_button(self, delta: int) -> None:
        buttons = [
            self.query_one("#approve", Button),
            self.query_one("#reject", Button),
            self.query_one("#always", Button),
        ]
        cur_idx = 0
        for idx, btn in enumerate(buttons):
            if btn.has_focus:
                cur_idx = idx
                break
        next_idx = (cur_idx + delta) % len(buttons)
        buttons[next_idx].focus()

    def on_key(self, event: events.Key) -> None:
        if self._decision is not None:
            return
        if event.key in ("left", "h"):
            event.stop()
            self._focus_relative_button(-1)
        elif event.key in ("right", "l"):
            event.stop()
            self._focus_relative_button(1)
        elif event.key == "y":
            event.stop()
            self.submit_decision("approve")
        elif event.key == "n":
            event.stop()
            self.submit_decision("reject")
        elif event.key == "a":
            event.stop()
            self.submit_decision("always")
        elif event.key == "escape":
            event.stop()
            self.submit_decision("reject")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.submit_decision(event.button.id or "reject")

    def submit_decision(self, decision: str) -> None:
        if self._decision is not None:
            return
        self._decision = decision
        if self.on_decision:
            self.on_decision(decision)

        # Replace button bar with decision status badge
        try:
            buttons_container = self.query_one("#confirm-buttons", Horizontal)
            buttons_container.remove()
        except Exception:
            pass

        badge_map = {
            "approve": "[bold green]✓ Approved[/bold green]",
            "always": "[bold yellow]✓ Always Allowed[/bold yellow]",
            "reject": "[bold red]✗ Rejected[/bold red]",
        }
        status_text = badge_map.get(decision, f"[dim]{decision}[/dim]")
        self.mount(Static(status_text, id="confirm-status"))

        # Return focus to chat input if available
        try:
            chat_input = self.app.screen.query_one("#chat-input")
            chat_input.focus()
        except Exception:
            pass

    # ── diff helper ─────────────────────────────────────────────

    def _compute_diff(self) -> str | None:
        if self._tool_name != "file_write":
            return None
        file_path = self._arguments.get("path", "")
        new_content = self._arguments.get("content", "")
        if not file_path:
            return None

        try:
            original = Path(file_path).expanduser().read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            original = []
        except Exception:
            return None

        new_lines = new_content.splitlines()
        diff_lines = list(difflib.unified_diff(
            original,
            new_lines,
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
        ))
        return "\n".join(diff_lines) if diff_lines else None


# Backwards compatibility alias
ConfirmModal = ConfirmCard


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
