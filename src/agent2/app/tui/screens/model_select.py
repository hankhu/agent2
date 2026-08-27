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
        self._models = get_available_models()

    def compose(self):  # type: ignore[override]
        with Vertical(id="model-dialog"):
            yield Static("[bold magenta]🤖 Model Selection[/bold magenta]\n")

            table: DataTable[str] = DataTable(cursor_type="row")
            table.add_columns("#", "Name", "Model", "Endpoint", "Source")
            for idx, m in enumerate(self._models, 1):
                table.add_row(
                    str(idx),
                    m["name"],
                    m["model"],
                    str(m["base_url"]),
                    str(m.get("source", "")),
                    key=m["name"],
                )
            yield table

            yield Input(
                placeholder="Enter number, alias or model name …",
                id="model-input",
            )

    def on_mount(self) -> None:
        """Keep keyboard focus in the search/input field."""
        self.query_one("#model-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        choice = event.value.strip()
        if not choice:
            self.dismiss("")
            return

        # Numeric selection
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(self._models):
                self.dismiss(self._models[idx]["name"])
                return

        # Name / model substring match (both directions so friendly labels like
        # "小米Mimo-v2.5" can resolve to the configured "mimo-v2.5").
        choice_l = choice.lower()
        for m in self._models:
            if (
                choice_l in m["name"].lower()
                or choice_l in m["model"].lower()
                or m["name"].lower() in choice_l
                or m["model"].lower() in choice_l
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
