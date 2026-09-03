"""Scrollable message list and individual message widgets."""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.widgets import Button, Collapsible, Markdown, Static

from agent2.app.tui.widgets.confirm_modal import ConfirmCard
from agent2.app.tui.widgets.tool_card import ToolCard


# ── Action Events ───────────────────────────────────────────────


class RewindRequested(Message):
    """Event posted when the user clicks the Rewind button on a message."""

    def __init__(self, message_widget: SelectableMessage, message_index: int | None = None) -> None:
        super().__init__()
        self.message_widget = message_widget
        self.message_index = message_index


class ForkRequested(Message):
    """Event posted when the user clicks the Fork button on a message."""

    def __init__(self, message_widget: SelectableMessage, message_index: int | None = None) -> None:
        super().__init__()
        self.message_widget = message_widget
        self.message_index = message_index


# ── Message List Container ──────────────────────────────────────


class MessageList(ScrollableContainer):
    """Vertically scrollable container for conversation messages."""

    def add_user_message(self, text: str, message_index: int | None = None) -> UserMessage:
        msg = UserMessage(text, message_index=message_index)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_assistant_message(self, content: str, message_index: int | None = None) -> AssistantMessage:
        msg = AssistantMessage(content, message_index=message_index)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_system_message(self, text: str) -> SystemMessage:
        msg = SystemMessage(text)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_thinking_block(
        self,
        content: str,
        step: int,
        elapsed: float = 0,
    ) -> ThinkingBlock:
        block = ThinkingBlock(content, step, elapsed)
        self.mount(block)
        block.scroll_visible()
        return block

    def add_tool_card(self, tool_name: str, arguments: dict) -> ToolCard:  # type: ignore[type-arg]
        card = ToolCard(tool_name, arguments)
        self.mount(card)
        card.scroll_visible()
        return card

    def add_confirm_card(
        self,
        tool_name: str,
        arguments: dict,  # type: ignore[type-arg]
        on_decision=None,
    ) -> ConfirmCard:
        card = ConfirmCard(tool_name, arguments, on_decision=on_decision)
        self.mount(card)
        card.scroll_visible()
        return card

    def deselect_all(self) -> None:
        """Clear selection state on all child messages."""
        for child in self.children:
            if hasattr(child, "remove_class"):
                child.remove_class("selected")

    def clear_messages(self) -> None:
        for child in list(self.children):
            child.remove()


# ── Message Widgets ─────────────────────────────────────────────


class SelectableMessage(Vertical):
    """Base class for selectable messages with Rewind and Fork action buttons."""

    can_focus = True

    def __init__(self, message_index: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.message_index = message_index

    def select(self) -> None:
        """Mark this message as selected and deselect siblings."""
        self.add_class("selected")
        if self.parent:
            for child in self.parent.children:
                if child is not self and hasattr(child, "remove_class"):
                    child.remove_class("selected")

    def on_click(self, event=None) -> None:
        self.select()

    def on_focus(self) -> None:
        self.select()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if "btn-rewind" in event.button.classes:
            self.post_message(RewindRequested(self, self.message_index))
        elif "btn-fork" in event.button.classes:
            self.post_message(ForkRequested(self, self.message_index))


class UserMessage(SelectableMessage):
    """A user-authored message bubble."""

    def __init__(self, text: str, message_index: int | None = None) -> None:
        super().__init__(message_index=message_index)
        self._text = text

    def compose(self):  # type: ignore[override]
        yield Static("[bold cyan]You[/bold cyan]")
        yield Static(self._text)
        with Horizontal(classes="message-actions"):
            yield Button("⏪ Rewind", classes="btn-action btn-rewind")
            yield Button("🍴 Fork", classes="btn-action btn-fork")


class AssistantMessage(SelectableMessage):
    """An assistant response rendered as Markdown."""

    def __init__(self, content: str, message_index: int | None = None) -> None:
        super().__init__(message_index=message_index)
        self._content = content

    def compose(self):  # type: ignore[override]
        yield Static("[bold green]Agent[/bold green]")
        yield Markdown(self._content)
        with Horizontal(classes="message-actions"):
            yield Button("⏪ Rewind", classes="btn-action btn-rewind")
            yield Button("🍴 Fork", classes="btn-action btn-fork")


class SystemMessage(Static):
    """A system/info message (e.g. "session cleared")."""

    def __init__(self, text: str) -> None:
        super().__init__(f"[dim italic]{text}[/dim italic]")


class ThinkingBlock(Collapsible):
    """Collapsible block showing the model's chain-of-thought reasoning."""

    def __init__(
        self,
        content: str,
        step: int,
        elapsed: float = 0,
    ) -> None:
        title = f"💭 Thinking — Step {step}"
        if elapsed > 0:
            title += f" ({elapsed:.1f}s)"
        super().__init__(
            Markdown(content),
            title=title,
            collapsed=True,
        )
