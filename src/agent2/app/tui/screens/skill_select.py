"""Skill management and selection screen — matching modern Copilot CLI aesthetic."""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from agent2.app.tui.widgets.nav_bar import TopTabBar
from agent2.context import SkillInfo, discover_skills


class SkillSearchInput(Input):
    """Search input that intercepts list navigation keys."""

    class NavigateUp(Message):
        pass

    class NavigateDown(Message):
        pass

    class ReloadRequested(Message):
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
        elif not self.value.strip() and event.key == "r":
            self.post_message(self.ReloadRequested())
            event.prevent_default()
            event.stop()
            return

        await super()._on_key(event)


class SkillSelectScreen(ModalScreen[str]):
    """Modern full-view skill picker and manager.

    - Type to search/filter skills in real-time
    - Up / Down: Navigate skills
    - Enter: Select highlighted skill to invoke
    - r: Reload skills from disk
    - Tab: Switch to the next top-level panel
    - Esc: Cancel / back to chat
    """

    DEFAULT_CSS = """
    SkillSelectScreen {
        background: #0d1117;
        color: #c9d1d9;
        layout: vertical;
        padding: 0;
        margin: 0;
    }

    #skill-container {
        height: 1fr;
        padding: 1 2 0 2;
        margin: 0;
    }

    #skill-tip {
        height: auto;
        margin-bottom: 1;
    }

    #skill-group-header {
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
        color: #8b949e;
        text-style: bold;
    }

    #skill-list {
        height: 1fr;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        scrollbar-size-vertical: 1;
    }

    #skill-list > .option-list--option-highlighted {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }

    #skill-list > .option-list--option:hover {
        background: #161b22;
    }

    #skill-search {
        height: auto;
        min-height: 1;
        background: #161b22;
        border: none;
        padding: 0 1;
        margin-top: 1;
        color: #c9d1d9;
    }

    #skill-search:focus {
        background: #21262d;
        border: none;
    }

    #skill-hint {
        height: 1;
        margin: 0;
        padding: 0 1;
        color: #8b949e;
        background: #0d1117;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel_or_close", "Close", priority=True),
        Binding("tab", "cycle_tab_next", "Next Tab", priority=True, show=False),
        Binding("shift+tab", "cycle_tab_prev", "Previous Tab", priority=True, show=False),
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("r", "reload_skills", "Reload", show=False),
    ]

    def __init__(self, skills: list[SkillInfo] | None = None) -> None:
        super().__init__()
        self._skills: list[SkillInfo] = list(skills) if skills is not None else discover_skills()
        self._filtered_skills: list[SkillInfo] = list(self._skills)

    def compose(self):  # type: ignore[override]
        yield TopTabBar(id="top-nav")
        with Vertical(id="skill-container"):
            yield Static(
                " [dodger_blue1]• Tip:[/dodger_blue1] [bold]/skills[/bold]\n"
                "   [dim]└ Browse, manage, and invoke skills (use /<skill_name> directly)[/dim]\n\n"
                "[dim]Skills provide specialized instructions, workflows, and tools.\n"
                "Directories: ~/.agent2/skills (primary), ~/.claude/skills, .agent2/skills\n"
                "Press Enter to select a skill to invoke, or 'r' to reload from disk.[/dim]",
                id="skill-tip",
            )
            count_str = f" ({len(self._skills)})" if self._skills else ""
            yield Static(f"Available skills{count_str}", id="skill-group-header")
            yield OptionList(id="skill-list")
            yield SkillSearchInput(placeholder="❯ Search skills...", id="skill-search")
            yield Static(
                "[dim]↑/↓ select  ·  enter invoke  ·  r reload  ·  tab next  ·  esc close[/dim]",
                id="skill-hint",
            )

    def on_mount(self) -> None:
        top_bar = self.query_one(TopTabBar)
        top_bar.active_tab = "skills"
        self._populate_options()
        self.query_one("#skill-search", SkillSearchInput).focus()

    def _populate_options(self, query: str = "") -> None:
        q = query.strip().lower()
        if q:
            self._filtered_skills = [
                s for s in self._skills
                if q in s.name.lower() or q in s.description.lower() or q in s.source.lower()
            ]
        else:
            self._filtered_skills = list(self._skills)

        opt_list = self.query_one("#skill-list", OptionList)
        opt_list.clear_options()

        if not self._filtered_skills:
            opt_list.add_option(Option("[dim]No matching skills found[/dim]", disabled=True))
            return

        from rich.markup import escape

        for s in self._filtered_skills:
            desc = escape(s.description[:55]) if s.description else "(no description)"
            src = f"({escape(s.source)})" if s.source else ""
            name = escape(s.name)
            line = f"  [bold]/{name:<22}[/bold]  [dim]·  {desc:<55}[/dim]  [dim dodger_blue1]{src}[/dim dodger_blue1]"
            opt_list.add_option(Option(line, id=s.name))

        opt_list.highlighted = 0

    def action_cycle_tab_next(self) -> None:
        self.query_one(TopTabBar).cycle_tab(1)

    def action_cycle_tab_prev(self) -> None:
        self.query_one(TopTabBar).cycle_tab(-1)

    def on_top_tab_bar_tab_selected(self, event: TopTabBar.TabSelected) -> None:
        if event.tab_id == "current":
            self.dismiss("")
        elif event.tab_id == "sessions":
            chat = None
            for s in reversed(self.app.screen_stack):
                if hasattr(s, "_open_sessions_dialog"):
                    chat = s
                    break
            self.dismiss("")
            if chat is not None:
                chat.call_next(chat._open_sessions_dialog)
        elif event.tab_id == "skills":
            self._populate_options(self.query_one("#skill-search", SkillSearchInput).value)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        opt_list = self.query_one("#skill-list", OptionList)
        if opt_list.highlighted is not None and self._filtered_skills:
            idx = opt_list.highlighted
            if 0 <= idx < len(self._filtered_skills):
                self.dismiss(self._filtered_skills[idx].name)
                return
        self.dismiss("")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            self.dismiss(str(event.option_id))

    def on_skill_search_input_navigate_up(self) -> None:
        self.action_nav_up()

    def on_skill_search_input_navigate_down(self) -> None:
        self.action_nav_down()

    def on_skill_search_input_reload_requested(self) -> None:
        self.action_reload_skills()

    def action_nav_up(self) -> None:
        opt_list = self.query_one("#skill-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted > 0:
            opt_list.highlighted -= 1

    def action_nav_down(self) -> None:
        opt_list = self.query_one("#skill-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted < opt_list.option_count - 1:
            opt_list.highlighted += 1

    def action_reload_skills(self) -> None:
        self._skills = discover_skills()
        header = self.query_one("#skill-group-header", Static)
        header.update(f"Available skills ({len(self._skills)})")
        search_input = self.query_one("#skill-search", SkillSearchInput)
        self._populate_options(search_input.value)

    def action_cancel_or_close(self) -> None:
        self.dismiss("")
