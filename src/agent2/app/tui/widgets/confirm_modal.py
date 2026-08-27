"""HITL confirmation modal for tool execution approval."""

from __future__ import annotations

import difflib
from pathlib import Path

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from agent2.app.tui.widgets.diff_view import DiffView


class ConfirmModal(ModalScreen[str]):
    """Blocking modal asking the user to approve a tool execution.

    Returns one of ``"approve"`` / ``"reject"`` / ``"always"`` via ``dismiss``.
    """

    BINDINGS = [
        ("y", "respond('approve')", "Approve"),
        ("n", "respond('reject')", "Reject"),
        ("a", "respond('always')", "Always Allow"),
        ("escape", "respond('reject')", "Cancel"),
    ]

    def __init__(self, tool_name: str, arguments: dict) -> None:  # type: ignore[type-arg]
        super().__init__()
        self._tool_name = tool_name
        self._arguments = arguments

    def compose(self):  # type: ignore[override]
        with Vertical(id="confirm-dialog"):
            yield Static("[bold yellow]⚠  Tool Execution Approval Required[/bold yellow]")
            yield Static(f"\n[bold]Tool:[/bold]  {self._tool_name}")

            args_lines = "\n".join(
                f"  {k}: {_truncate(str(v), 200)}" for k, v in self._arguments.items()
            )
            yield Static(f"[bold]Arguments:[/bold]\n{args_lines}")

            # Show inline diff for file_write
            diff = self._compute_diff()
            if diff:
                yield DiffView(diff, filename=str(self._arguments.get("path", "")))

            with Horizontal(id="confirm-buttons"):
                yield Button("[y] Approve", variant="success", id="approve")
                yield Button("[n] Reject", variant="error", id="reject")
                yield Button("[a] Always Allow", variant="warning", id="always")

    # ── actions ─────────────────────────────────────────────────

    def action_respond(self, decision: str) -> None:
        self.dismiss(decision)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "reject")

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


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
