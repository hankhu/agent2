"""Session management modal screen — supporting list, resume, rename, and delete."""

from __future__ import annotations

import time
from typing import Any

from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from agent2.app.tui.session import SessionManager


class SessionSelectScreen(ModalScreen[str]):
    """Modal overlay for session management (resume, rename, delete).

    - Enter: Resume selected session
    - e / r: Rename selected session
    - d / delete: Delete selected session
    - Esc: Close dialog (or cancel rename)
    """

    BINDINGS = [
        Binding("escape", "cancel_or_close", "Close"),
        Binding("e", "edit_title", "Rename"),
        Binding("r", "edit_title", "Rename"),
        Binding("d", "delete_session", "Delete"),
    ]

    def __init__(
        self,
        sessions: list[dict[str, Any]],
        session_manager: SessionManager | None = None,
    ) -> None:
        super().__init__()
        self._sessions = list(sessions)
        self._session_manager = session_manager or SessionManager()
        self._editing_session: dict[str, Any] | None = None

    def compose(self):  # type: ignore[override]
        with Vertical(id="session-dialog"):
            yield Static("[bold cyan]💾 Session Management[/bold cyan]", id="session-header")

            table: DataTable[str] = DataTable(cursor_type="row")
            table.add_column("#", width=4)
            table.add_column("Title", width=48)
            table.add_column("ID", width=12)
            table.add_column("Saved", width=18)
            self._populate_table(table)
            yield table

            yield Input(
                placeholder="Enter new session title and press Enter…",
                id="rename-input",
            )

            yield Static(
                "[bold cyan]Enter[/bold cyan] Resume  │  "
                "[bold yellow]e[/bold yellow] Rename  │  "
                "[bold red]d[/bold red] Delete  │  "
                "[bold dim]Esc[/bold dim] Close",
                id="session-hint",
            )

    def on_mount(self) -> None:
        rename_input = self.query_one("#rename-input", Input)
        rename_input.styles.display = "none"
        self.query_one(DataTable).focus()

    def _populate_table(self, table: DataTable[str] | None = None) -> None:
        if table is None:
            try:
                table = self.query_one(DataTable)
            except Exception:
                return
        table.clear()
        for idx, s in enumerate(self._sessions, 1):
            saved = (
                time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(float(s.get("saved_at", 0) or 0)),
                )
                if s.get("saved_at")
                else ""
            )
            table.add_row(
                str(idx),
                s.get("title") or "(untitled)",
                str(s.get("id", ""))[:12],
                saved,
                key=str(s.get("id", "")),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key and key.value:
            self.dismiss(str(key.value))

    def action_edit_title(self) -> None:
        """Open inline input to rename the highlighted session."""
        rename_input = self.query_one("#rename-input", Input)
        if rename_input.styles.display == "block":
            return

        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._sessions):
            self._editing_session = self._sessions[row]
            rename_input.value = self._editing_session.get("title", "")
            rename_input.styles.display = "block"
            rename_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle submission of the new session title."""
        rename_input = self.query_one("#rename-input", Input)
        rename_input.styles.display = "none"

        if self._editing_session:
            new_title = event.value.strip()
            if new_title:
                sess_id = str(self._editing_session.get("id", ""))
                try:
                    self._session_manager.rename(sess_id, new_title)
                    self._editing_session["title"] = new_title
                    # If current session is renamed, update app state
                    app = self.app
                    if getattr(app, "session_id", None) == sess_id:
                        app.session_title = new_title  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._editing_session = None

        self._populate_table()
        self.query_one(DataTable).focus()

    def action_delete_session(self) -> None:
        """Delete the highlighted session from disk and table."""
        rename_input = self.query_one("#rename-input", Input)
        if rename_input.styles.display == "block":
            return

        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._sessions):
            target = self._sessions.pop(row)
            sess_id = str(target.get("id", ""))
            try:
                self._session_manager.delete(sess_id)
            except Exception:
                pass

            if not self._sessions:
                self.dismiss("")
                return

            self._populate_table()
            new_row = min(row, len(self._sessions) - 1)
            table.cursor_coordinate = Coordinate(new_row, 0)

    def action_cancel_or_close(self) -> None:
        """Esc handler: dismiss rename input if open, else close dialog."""
        rename_input = self.query_one("#rename-input", Input)
        if rename_input.styles.display == "block":
            rename_input.styles.display = "none"
            self._editing_session = None
            self.query_one(DataTable).focus()
        else:
            self.dismiss("")

