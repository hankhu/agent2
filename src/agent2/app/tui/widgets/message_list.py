"""Scrollable message list and individual message widgets."""

from __future__ import annotations

from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Collapsible, Markdown, Static

from agent2.app.tui.widgets.confirm_modal import ConfirmCard
from agent2.app.tui.widgets.tool_card import ToolCard


class MessageList(ScrollableContainer):
    """Vertically scrollable container for conversation messages."""

    def add_user_message(self, text: str) -> "UserMessage":
        msg = UserMessage(text)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_assistant_message(self, content: str) -> "AssistantMessage":
        msg = AssistantMessage(content)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_system_message(self, text: str) -> "SystemMessage":
        msg = SystemMessage(text)
        self.mount(msg)
        msg.scroll_visible()
        return msg

    def add_thinking_block(
        self,
        content: str,
        step: int,
        elapsed: float = 0,
    ) -> "ThinkingBlock":
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

    def clear_messages(self) -> None:
        for child in list(self.children):
            child.remove()


# ── Message Widgets ─────────────────────────────────────────────


class UserMessage(Vertical):
    """A user-authored message bubble."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self):  # type: ignore[override]
        yield Static("[bold cyan]You[/bold cyan]")
        yield Static(self._text)


class AssistantMessage(Vertical):
    """An assistant response rendered as Markdown."""

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self):  # type: ignore[override]
        yield Static("[bold green]Agent[/bold green]")
        yield Markdown(self._content)


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
