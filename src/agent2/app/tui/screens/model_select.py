"""Model selection modal screen."""

from __future__ import annotations

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Select, Static

from agent2.app.chat import get_available_models


class ModelSelectScreen(ModalScreen[str]):
    """Modal overlay with a drop-down menu for interactive model selection.

    Dismisses with the chosen model name (or empty string on cancel).
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._all_models = get_available_models()
        self._models = self._all_models  # backward-compatible alias

    def compose(self):  # type: ignore[override]
        with Vertical(id="model-dialog"):
            yield Static("[bold magenta]🤖 Model Selection[/bold magenta]")

            options: list[tuple[str, str]] = []
            for m in self._all_models:
                provider = m.get("provider") or m.get("source") or m["name"]
                model_name = m.get("model", m["name"])
                label = f"[{provider}] {model_name}"
                options.append((label, m["name"]))

            yield Select[str](
                options=options,
                prompt="Select a model… (Enter or click to expand)",
                allow_blank=True,
                id="model-select",
            )

            yield Input(
                placeholder="Or enter custom model ID… (Enter to submit)",
                id="model-input",
            )

    def on_mount(self) -> None:
        """Keep keyboard focus on the drop-down menu on open."""
        self.query_one("#model-select", Select).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle selection from the drop-down menu."""
        if event.value != Select.BLANK and event.value is not None:
            self.dismiss(str(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle submission of a custom model identifier."""
        choice = event.value.strip()
        if not choice:
            self.dismiss("")
            return

        choice_l = choice.lower()
        for m in self._all_models:
            if (
                choice_l in m["name"].lower()
                or choice_l in m["model"].lower()
                or m["name"].lower() in choice_l
                or m["model"].lower() in choice_l
                or choice_l in m.get("provider", "").lower()
            ):
                self.dismiss(m["name"])
                return

        self.dismiss(choice)

    def action_cancel(self) -> None:
        self.dismiss("")

