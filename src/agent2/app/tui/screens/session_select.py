"""Session selection modal screen."""

from __future__ import annotations

import time
from typing import Any

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static


class SessionSelectScreen(ModalScreen[str]):
    """Modal overlay listing saved sessions for selection.

    Dismisses with the chosen session id (or empty string on cancel).
    Arrow keys navigate the table; Enter selects the highlighted row.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, sessions: list[dict[str, Any]]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self):  # type: ignore[override]
        with Vertical(id="session-dialog"):
            yield Static("[bold cyan]💾 Session List[/bold cyan]\n")

            table: DataTable[str] = DataTable(cursor_type="row")
            table.add_column("#", width=4)
            table.add_column("Title", width=50)
            table.add_column("ID", width=12)
            table.add_column("Saved", width=20)
            for idx, s in enumerate(self._sessions, 1):
                saved = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(float(s.get("saved_at", 0) or 0)),
                ) if s.get("saved_at") else ""
                table.add_row(
                    str(idx),
                    s.get("title") or "(untitled)",
                    str(s.get("id", ""))[:12],
                    saved,
                    key=str(s.get("id", "")),
                )
            yield table

    def on_mount(self) -> None:
        self.query_one(DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key and key.value:
            self.dismiss(str(key.value))

    def action_cancel(self) -> None:
        self.dismiss("")
