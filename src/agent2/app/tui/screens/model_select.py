"""Model selection modal screen."""

from __future__ import annotations

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from agent2.app.chat import get_available_models


class ModelSelectScreen(ModalScreen[str]):
    """Modal overlay listing available models for interactive selection.

    Dismisses with the chosen model name (or empty string on cancel).
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._all_models = get_available_models()
        self._models = self._all_models  # backward-compatible alias
        self._visible_models = list(self._all_models)

    def compose(self):  # type: ignore[override]
        with Vertical(id="model-dialog"):
            yield Static("[bold magenta]🤖 Model Selection[/bold magenta]\n")

            yield Input(
                placeholder="Filter models… (Enter to select)",
                id="model-input",
            )

            table: DataTable[str] = DataTable(cursor_type="row")
            table.add_column("#", width=4)
            table.add_column("Provider", width=14)
            table.add_column("Model", width=50)
            self._populate_table(table)
            yield table

    def on_mount(self) -> None:
        """Keep keyboard focus in the search/input field."""
        self.query_one("#model-input", Input).focus()

    def _populate_table(self, table: DataTable[str]) -> None:
        table.clear()
        for idx, m in enumerate(self._visible_models, 1):
            table.add_row(
                str(idx),
                m.get("provider") or m["name"],
                m["model"],
                key=m["name"],
            )

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            self._visible_models = [
                m for m in self._all_models
                if (
                    q in m["name"].lower()
                    or q in m["model"].lower()
                    or q in m.get("provider", "").lower()
                    or q in m.get("source", "").lower()
                    or m["name"].lower() in q
                    or m["model"].lower() in q
                    or m.get("provider", "").lower() in q
                )
            ]
        else:
            self._visible_models = list(self._all_models)
        try:
            table = self.query_one(DataTable)
        except Exception:
            return
        self._populate_table(table)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        choice = event.value.strip()
        if not choice:
            self.dismiss("")
            return

        # Numeric selection against the currently filtered list.
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(self._visible_models):
                self.dismiss(self._visible_models[idx]["name"])
                return

        # Name / model / provider substring match (both directions so friendly
        # labels like "小米Mimo-v2.5" can resolve to "mimo-v2.5").
        choice_l = choice.lower()
        for m in self._visible_models:
            if (
                choice_l in m["name"].lower()
                or choice_l in m["model"].lower()
                or m["name"].lower() in choice_l
                or m["model"].lower() in choice_l
                or choice_l in m.get("provider", "").lower()
            ):
                self.dismiss(m["name"])
                return

        # Treat as a custom model identifier
        self.dismiss(choice)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key and key.value:
            self.dismiss(str(key.value))

    def action_cancel(self) -> None:
        self.dismiss("")
