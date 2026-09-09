"""Session management screen — modern full-screen selection matching Copilot CLI aesthetic."""

from __future__ import annotations

import time
from typing import Any

from textual import events
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from agent2.app.tui.screens.help import HelpScreen
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.nav_bar import TopTabBar


def _fmt_time_ago(ts: float) -> str:
    """Format timestamp into human-readable relative time."""
    if not ts:
        return ""
    diff = time.time() - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    if diff < 86400 * 7:
        return f"{int(diff // 86400)}d ago"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


class SessionSearchInput(Input):
    """Search input that intercepts list navigation and action keys."""

    class NavigateUp(Message):
        pass

    class NavigateDown(Message):
        pass

    class DeleteRequested(Message):
        pass

    class RenameRequested(Message):
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
        elif event.key == "delete" or (not self.value.strip() and event.key == "d"):
            self.post_message(self.DeleteRequested())
            event.prevent_default()
            event.stop()
            return
        elif not self.value.strip() and event.key in ("e", "r"):
            self.post_message(self.RenameRequested())
            event.prevent_default()
            event.stop()
            return

        await super()._on_key(event)


class SessionSelectScreen(ModalScreen[str]):
    """Modern full-view session picker.

    - Type to search/filter sessions in real-time
    - Up / Down: Navigate sessions
    - Enter: Select highlighted session to resume (or submit rename)
    - e / r: Rename highlighted session
    - d / delete: Delete highlighted session
    - Esc: Cancel / back to current session
    """

    DEFAULT_CSS = """
    SessionSelectScreen {
        background: #0d1117;
        color: #c9d1d9;
        layout: vertical;
        padding: 0;
        margin: 0;
    }

    #session-container {
        height: 1fr;
        padding: 1 2 0 2;
        margin: 0;
    }

    #session-tip {
        height: auto;
        margin-bottom: 1;
    }

    #session-group-header {
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
        color: #8b949e;
        text-style: bold;
    }

    #session-body {
        height: 1fr;
        layout: horizontal;
        margin: 0;
        padding: 0;
    }

    #session-list {
        width: 1fr;
        height: 100%;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        scrollbar-size-vertical: 1;
    }

    #session-list > .option-list--option-highlighted {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }

    #session-list > .option-list--option:hover {
        background: #161b22;
    }

    #session-preview-col {
        width: 1fr;
        height: 100%;
        background: #161b22;
        border-left: solid #30363d;
        padding: 0 1;
        margin: 0;
    }

    #session-preview-scroll {
        height: 1fr;
        scrollbar-size-vertical: 1;
    }

    #session-preview-content {
        padding: 0 1;
        color: #c9d1d9;
    }

    #session-search {
        height: auto;
        min-height: 1;
        background: #161b22;
        border: none;
        padding: 0 1;
        margin-top: 1;
        color: #c9d1d9;
    }

    #session-search:focus {
        background: #21262d;
        border: none;
    }

    #session-hint {
        height: 1;
        margin: 0;
        padding: 0 1;
        color: #8b949e;
        background: #0d1117;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel_or_close", "Close", priority=True),
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("e", "edit_title", "Rename", show=False),
        Binding("r", "edit_title", "Rename", show=False),
        Binding("d", "delete_session", "Delete", show=False),
    ]

    def __init__(
        self,
        sessions: list[dict[str, Any]],
        session_manager: SessionManager | None = None,
    ) -> None:
        super().__init__()
        self._sessions = list(sessions)
        self._session_manager = session_manager or SessionManager()
        self._filtered_sessions: list[dict[str, Any]] = list(sessions)
        self._renaming_session: dict[str, Any] | None = None
        self._preview_cache: dict[str, str] = {}

    def compose(self):  # type: ignore[override]
        yield TopTabBar(id="top-nav")
        with Vertical(id="session-container"):
            yield Static(
                " [dodger_blue1]• Tip:[/dodger_blue1] [bold]/sessions[/bold]\n"
                "   [dim]└ Manage, resume, rename, or delete conversation sessions[/dim]\n\n"
                "[dim]Resume a saved session to restore your previous context and conversation history.\n"
                "Use 'e' to rename, 'd' to delete, and Enter to select.[/dim]",
                id="session-tip",
            )
            yield Static("Saved sessions", id="session-group-header")
            with Horizontal(id="session-body"):
                yield OptionList(id="session-list")
                with Vertical(id="session-preview-col"):
                    with VerticalScroll(id="session-preview-scroll"):
                        yield Static(id="session-preview-content")
            yield SessionSearchInput(placeholder="❯ Search sessions...", id="session-search")
            yield Static(
                "[dim]↑/↓ to navigate  ·  enter to select  ·  e rename  ·  d delete  ·  esc to cancel[/dim]",
                id="session-hint",
            )

    def on_mount(self) -> None:
        top_bar = self.query_one(TopTabBar)
        top_bar.active_tab = "sessions"
        self._populate_options()
        self.query_one("#session-search", SessionSearchInput).focus()

    def _show_preview(self, session_id: str | None = None) -> None:
        try:
            preview_widget = self.query_one("#session-preview-content", Static)
        except Exception:
            return
        if not session_id:
            preview_widget.update("[dim](No session selected)[/dim]")
            return
        if session_id not in self._preview_cache:
            self._preview_cache[session_id] = self._session_manager.get_session_preview(session_id)
        preview_widget.update(self._preview_cache[session_id])

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option and event.option.id:
            self._show_preview(str(event.option.id))
        elif event.option_index is not None and 0 <= event.option_index < len(self._filtered_sessions):
            self._show_preview(str(self._filtered_sessions[event.option_index].get("id", "")))

    def _populate_options(self, query: str = "") -> None:
        q = query.strip().lower()
        if q:
            self._filtered_sessions = [
                s for s in self._sessions
                if q in (s.get("title") or "").lower()
                or q in str(s.get("id", "")).lower()
                or q in str(s.get("preview", "")).lower()
            ]
        else:
            self._filtered_sessions = list(self._sessions)

        opt_list = self.query_one("#session-list", OptionList)
        opt_list.clear_options()

        if not self._filtered_sessions:
            opt_list.add_option(Option("[dim]No matching sessions found[/dim]", disabled=True))
            self._show_preview(None)
            return

        for s in self._filtered_sessions:
            title = s.get("title") or "(untitled)"
            sid = str(s.get("id", ""))[:8]
            saved_at = float(s.get("saved_at", 0) or 0)
            time_str = _fmt_time_ago(saved_at)
            
            line = f"  {title:<35}  [dim]·  {sid}  ·  {time_str}[/dim]"
            opt_list.add_option(Option(line, id=str(s.get("id", ""))))

        opt_list.highlighted = 0
        first_id = str(self._filtered_sessions[0].get("id", ""))
        self._show_preview(first_id)

    def on_top_tab_bar_tab_selected(self, event: TopTabBar.TabSelected) -> None:
        if event.tab_id == "current":
            self.dismiss("")
        elif event.tab_id == "skills":
            from agent2.app.tui.screens.skill_select import SkillSelectScreen
            self.dismiss("")
            self.app.push_screen(SkillSelectScreen())
        elif event.tab_id == "help":
            self.app.push_screen(HelpScreen())

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._renaming_session is not None:
            return
        self._populate_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._renaming_session is not None:
            new_title = event.value.strip()
            if new_title:
                sess_id = str(self._renaming_session.get("id", ""))
                try:
                    self._session_manager.rename(sess_id, new_title)
                    self._renaming_session["title"] = new_title
                    self._preview_cache.pop(sess_id, None)
                    app = self.app
                    if getattr(app, "session_id", None) == sess_id:
                        app.session_title = new_title  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._exit_rename_mode()
            return

        opt_list = self.query_one("#session-list", OptionList)
        h = opt_list.highlighted
        if h is not None and 0 <= h < len(self._filtered_sessions):
            sess_id = str(self._filtered_sessions[h].get("id", ""))
            self.dismiss(sess_id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.dismiss(str(event.option.id))

    def on_session_search_input_navigate_up(self, event: SessionSearchInput.NavigateUp) -> None:
        opt_list = self.query_one("#session-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted > 0:
            opt_list.highlighted -= 1

    def on_session_search_input_navigate_down(self, event: SessionSearchInput.NavigateDown) -> None:
        opt_list = self.query_one("#session-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted < opt_list.option_count - 1:
            opt_list.highlighted += 1

    def on_session_search_input_rename_requested(self, event: SessionSearchInput.RenameRequested) -> None:
        self.action_edit_title()

    def on_session_search_input_delete_requested(self, event: SessionSearchInput.DeleteRequested) -> None:
        self.action_delete_session()

    def action_nav_up(self) -> None:
        self.on_session_search_input_navigate_up(SessionSearchInput.NavigateUp())

    def action_nav_down(self) -> None:
        self.on_session_search_input_navigate_down(SessionSearchInput.NavigateDown())

    def action_edit_title(self) -> None:
        opt_list = self.query_one("#session-list", OptionList)
        h = opt_list.highlighted
        if h is not None and 0 <= h < len(self._filtered_sessions):
            self._renaming_session = self._filtered_sessions[h]
            inp = self.query_one("#session-search", SessionSearchInput)
            inp.placeholder = "Enter new session title and press Enter…"
            inp.value = self._renaming_session.get("title", "")
            inp.focus()

    def _exit_rename_mode(self) -> None:
        self._renaming_session = None
        inp = self.query_one("#session-search", SessionSearchInput)
        inp.placeholder = "❯ Search sessions..."
        inp.value = ""
        self._populate_options()
        inp.focus()

    def action_delete_session(self) -> None:
        if self._renaming_session is not None:
            return
        opt_list = self.query_one("#session-list", OptionList)
        h = opt_list.highlighted
        if h is not None and 0 <= h < len(self._filtered_sessions):
            target = self._filtered_sessions[h]
            sess_id = str(target.get("id", ""))
            try:
                self._session_manager.delete(sess_id)
            except Exception:
                pass
            self._preview_cache.pop(sess_id, None)
            if target in self._sessions:
                self._sessions.remove(target)

            if not self._sessions:
                self.dismiss("")
                return

            inp = self.query_one("#session-search", SessionSearchInput)
            self._populate_options(inp.value)

    def action_cancel_or_close(self) -> None:
        if self._renaming_session is not None:
            self._exit_rename_mode()
        else:
            self.dismiss("")
