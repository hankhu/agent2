"""Model selection modal screen — matching modern Copilot CLI aesthetic."""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from agent2.app.chat import get_available_models, resolve_provider_or_host
from agent2.app.tui.widgets.nav_bar import TopTabBar


class ModelSearchInput(Input):
    """Search input that intercepts list navigation keys."""

    class NavigateUp(Message):
        pass

    class NavigateDown(Message):
        pass

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "up":
            self.post_message(self.NavigateUp())
            event.prevent_default()
            event.stop()
            return
        elif event.key == "down":
            self.post_message(self.NavigateDown())
            event.prevent_default()
            event.stop()
            return

        await super()._on_key(event)


class ModelSelectScreen(ModalScreen[str]):
    """Modern full-view model selection screen.

    - Type to search/filter models in real-time
    - Up / Down: Navigate models list
    - Enter: Select highlighted model (or submit custom model string)
    - Esc: Cancel / close dialog
    """

    DEFAULT_CSS = """
    ModelSelectScreen {
        background: #0d1117;
        color: #c9d1d9;
        layout: vertical;
        padding: 0;
        margin: 0;
    }

    #model-container {
        height: 1fr;
        padding: 1 2 0 2;
        margin: 0;
    }

    #model-tip {
        height: auto;
        margin-bottom: 1;
    }

    #model-group-header {
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
        color: #8b949e;
        text-style: bold;
    }

    #model-list {
        height: 1fr;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        scrollbar-size-vertical: 1;
    }

    #model-list > .option-list--option-highlighted {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }

    #model-list > .option-list--option:hover {
        background: #161b22;
    }

    #model-input {
        height: auto;
        min-height: 1;
        background: #161b22;
        border: none;
        padding: 0 1;
        margin-top: 1;
        color: #c9d1d9;
    }

    #model-input:focus {
        background: #21262d;
        border: none;
    }

    #model-hint {
        height: 1;
        margin: 0;
        padding: 0 1;
        color: #8b949e;
        background: #0d1117;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("tab", "cycle_tab_next", "Next Tab", priority=True, show=False),
        Binding("shift+tab", "cycle_tab_prev", "Previous Tab", priority=True, show=False),
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._all_models = get_available_models()
        self._models = self._all_models  # backward-compatible alias
        self._filtered_models = list(self._all_models)

    def compose(self):  # type: ignore[override]
        yield TopTabBar(id="top-nav")
        with Vertical(id="model-container"):
            yield Static(
                " [dodger_blue1]• Tip:[/dodger_blue1] [bold]/model[/bold]\n"
                "   [dim]└ Select active LLM model or enter custom model identifier[/dim]\n\n"
                "[dim]Auto routes based on your task, real-time system health, and model performance.\n"
                "Changes apply to this session only. Use '/model [name]' to switch model directly.[/dim]",
                id="model-tip",
            )
            yield Static("Available models", id="model-group-header")
            yield OptionList(id="model-list")
            yield ModelSearchInput(placeholder="❯ Search models...", id="model-input")
            yield Static(
                "[dim]↑/↓ select  ·  enter choose  ·  tab next  ·  esc cancel[/dim]",
                id="model-hint",
            )

    def on_mount(self) -> None:
        top_bar = self.query_one(TopTabBar)
        top_bar.active_tab = "current"
        self._populate_options()
        self.query_one("#model-input", ModelSearchInput).focus()

    def _populate_options(self, query: str = "") -> None:
        q = query.strip().lower()
        if q:
            self._filtered_models = [
                m for m in self._all_models
                if q in m.get("name", "").lower()
                or q in m.get("model", "").lower()
                or q in resolve_provider_or_host(m.get("provider"), m.get("base_url")).lower()
            ]
        else:
            self._filtered_models = list(self._all_models)

        opt_list = self.query_one("#model-list", OptionList)
        opt_list.clear_options()

        if not self._filtered_models:
            opt_list.add_option(Option("[dim]No matching models (press Enter to use custom input)[/dim]", disabled=True))
            return

        for m in self._filtered_models:
            name = m.get("name", "")
            provider = resolve_provider_or_host(m.get("provider"), m.get("base_url"))
            model_id = m.get("model", "")
            meta = f"\\[{provider}] {model_id}" if provider else model_id
            ctx = m.get("context_window_str") or ""
            pricing_rate = m.get("pricing_rate") or ""
            details = [meta]
            if ctx:
                details.append(f"ctx {ctx}")
            if pricing_rate and pricing_rate != "Free":
                details.append(pricing_rate)
            details_str = "  ·  ".join(details)
            line = f"  {name:<28}  [dim]·  {details_str}[/dim]"
            opt_list.add_option(Option(line, id=name))

        opt_list.highlighted = 0

    def action_cycle_tab_next(self) -> None:
        self.query_one(TopTabBar).cycle_tab(1)

    def action_cycle_tab_prev(self) -> None:
        self.query_one(TopTabBar).cycle_tab(-1)

    def on_top_tab_bar_tab_selected(self, event: TopTabBar.TabSelected) -> None:
        if event.tab_id == "current":
            self.dismiss("")
        elif event.tab_id in ("sessions", "skills"):
            chat = None
            method_name = (
                "_open_sessions_dialog" if event.tab_id == "sessions" else "_open_skills_dialog"
            )
            for s in reversed(self.app.screen_stack):
                if hasattr(s, method_name):
                    chat = s
                    break
            self.dismiss("")
            if chat is not None:
                chat.call_next(getattr(chat, method_name))
        elif event.tab_id == "models":
            self._populate_options(self.query_one("#model-search").value)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        choice = event.value.strip()
        opt_list = self.query_one("#model-list", OptionList)
        h = opt_list.highlighted

        if h is not None and 0 <= h < len(self._filtered_models):
            self.dismiss(self._filtered_models[h]["name"])
            return

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
                or choice_l in resolve_provider_or_host(m.get("provider"), m.get("base_url")).lower()
            ):
                self.dismiss(m["name"])
                return

        self.dismiss(choice)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.dismiss(str(event.option.id))

    def on_model_search_input_navigate_up(self, event: ModelSearchInput.NavigateUp) -> None:
        opt_list = self.query_one("#model-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted > 0:
            opt_list.highlighted -= 1

    def on_model_search_input_navigate_down(self, event: ModelSearchInput.NavigateDown) -> None:
        opt_list = self.query_one("#model-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted < opt_list.option_count - 1:
            opt_list.highlighted += 1

    def action_nav_up(self) -> None:
        self.on_model_search_input_navigate_up(ModelSearchInput.NavigateUp())

    def action_nav_down(self) -> None:
        self.on_model_search_input_navigate_down(ModelSearchInput.NavigateDown())

    def action_cancel(self) -> None:
        self.dismiss("")
