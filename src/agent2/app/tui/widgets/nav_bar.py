"""Top navigation tab bar widget — Current, Sessions, and Skills tabs."""

from __future__ import annotations

from textual import events
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class TabItem(Static):
    """A single tab in the TopTabBar."""

    can_focus = True

    def __init__(self, label: str, tab_id: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(label, id=f"tab-{tab_id}", classes="top-tab", **kwargs)
        self.tab_id = tab_id

    def on_click(self) -> None:
        self.post_message(TopTabBar.TabSelected(self.tab_id))

    def on_key(self, event: events.Key) -> None:
        parent = self.parent
        if event.key == "tab" and isinstance(parent, TopTabBar):
            parent.cycle_tab()
            event.prevent_default()
            event.stop()
            return
        if event.key == "shift+tab" and isinstance(parent, TopTabBar):
            parent.cycle_tab(-1)
            event.prevent_default()
            event.stop()
            return
        if event.key in ("enter", "space"):
            try:
                chat_input = self.screen.query_one("#chat-input")
                if self.tab_id == "current" and getattr(chat_input, "text", "").strip():
                    text = chat_input.text.strip()
                    chat_input.clear()
                    chat_input.focus()
                    chat_input.post_message(chat_input.Submitted(text))
                    event.prevent_default()
                    event.stop()
                    return
            except Exception:
                pass
            self.post_message(TopTabBar.TabSelected(self.tab_id))
            event.prevent_default()
            event.stop()
            return
        if (
            event.character
            and event.character.isprintable()
            and event.key not in ("tab", "shift+tab", "enter", "escape")
        ):
            try:
                chat_input = self.screen.query_one("#chat-input")
                chat_input.focus()
                empty = not getattr(chat_input, "text", "").strip()
                if empty and event.character in ("?", "？"):
                    action = getattr(self.screen, "action_toggle_shortcuts", None)
                    if action is not None:
                        action()
                        event.prevent_default()
                        event.stop()
                        return
                if empty and event.character in ("+", "＋"):
                    action = getattr(self.screen, "action_tab_sessions", None)
                    if action is not None:
                        action()
                        event.prevent_default()
                        event.stop()
                        return
                chat_input.insert(event.character)
                event.prevent_default()
                event.stop()
            except Exception:
                pass


class TopTabBar(Widget):
    """Top navigation bar showing Current, Sessions, and Skills tabs."""

    DEFAULT_CSS = """
    TopTabBar {
        height: 1;
        width: 100%;
        layout: horizontal;
        background: #0d1117;
        padding: 0 1;
        margin: 0;
    }

    .top-tab {
        height: 1;
        width: auto;
        min-width: 9;
        padding: 0 1;
        margin: 0 1 0 0;
        color: #8b949e;
        background: transparent;
        text-align: center;
    }

    .top-tab:hover, .top-tab:focus {
        color: #c9d1d9;
        background: #161b22;
    }

    .top-tab.active {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }
    """

    TABS = [
        ("current", "Current"),
        ("sessions", "Sessions"),
        ("skills", "Skills"),
    ]

    active_tab: reactive[str] = reactive("current")

    class TabSelected(Message):
        """Posted when a tab is clicked or selected."""

        def __init__(self, tab_id: str) -> None:
            super().__init__()
            self.tab_id = tab_id

    def compose(self):  # type: ignore[override]
        for tab_id, label in self.TABS:
            yield TabItem(label, tab_id=tab_id)

    def on_mount(self) -> None:
        self._update_tab_classes(self.active_tab)

    def watch_active_tab(self, new_tab: str) -> None:
        self._update_tab_classes(new_tab)

    def _update_tab_classes(self, active_id: str) -> None:
        for tab_id, _ in self.TABS:
            try:
                item = self.query_one(f"#tab-{tab_id}", TabItem)
                if tab_id == active_id:
                    item.add_class("active")
                else:
                    item.remove_class("active")
            except Exception:
                pass

    def cycle_tab(self, direction: int = 1) -> str:
        """Cycle to next or previous tab and emit TabSelected."""
        ids = [t[0] for t in self.TABS]
        try:
            curr_idx = ids.index(self.active_tab)
        except ValueError:
            curr_idx = 0
        next_idx = (curr_idx + direction) % len(ids)
        next_tab = ids[next_idx]
        self.active_tab = next_tab
        self.post_message(self.TabSelected(next_tab))
        return next_tab
