"""Scrollable message list and individual message widgets."""

from __future__ import annotations

from typing import Any

from textual import events
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


class RetryRequested(Message):
    """Event posted when the user clicks the Retry button on a message."""

    def __init__(self, message_widget: SelectableMessage, message_index: int | None = None) -> None:
        super().__init__()
        self.message_widget = message_widget
        self.message_index = message_index


class ContinueRequested(Message):
    """Event posted when the user clicks the Continue button on a message."""

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

    def on_mount(self) -> None:
        self.anchor(True)

    def on_key(self, event: events.Key) -> None:
        if (
            event.character
            and event.character.isprintable()
            and event.key
            not in ("tab", "shift+tab", "enter", "escape", "up", "down", "pageup", "pagedown", "home", "end")
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

    def _maybe_scroll_to_bottom(self) -> None:
        """Scroll to the bottom if the user hasn't actively scrolled away."""
        if not self._anchor_released or self.is_vertical_scroll_end:
            self.scroll_end(animate=False)

    def add_user_message(self, text: str, message_index: int | None = None) -> UserMessage:
        msg = UserMessage(text, message_index=message_index)
        msg._await_mount = self.mount(msg)
        self._anchor_released = False
        self.scroll_end(animate=False)
        return msg


    def add_assistant_message(
        self,
        content: str,
        message_index: int | None = None,
        can_continue: bool = False,
    ) -> AssistantMessage:
        msg = AssistantMessage(content, message_index=message_index, can_continue=can_continue)
        self.mount(msg)
        self._maybe_scroll_to_bottom()
        return msg

    def add_system_message(self, text: str) -> SystemMessage:
        msg = SystemMessage(text)
        self.mount(msg)
        self._maybe_scroll_to_bottom()
        return msg

    def add_thinking_block(
        self,
        content: str,
        step: int,
        elapsed: float = 0,
    ) -> ThinkingBlock:
        block = ThinkingBlock(content, step, elapsed)
        self.mount(block)
        self._maybe_scroll_to_bottom()
        return block

    def add_tool_card(
        self,
        tool_name: str,
        arguments: dict,  # type: ignore[type-arg]
        result: str | None = None,
        is_error: bool = False,
    ) -> ToolCard:
        card = ToolCard(tool_name, arguments, result=result, is_error=is_error)
        self.mount(card)
        self._maybe_scroll_to_bottom()
        return card

    def add_confirm_card(
        self,
        tool_name: str,
        arguments: dict,  # type: ignore[type-arg]
        on_decision=None,
    ) -> ConfirmCard:
        card = ConfirmCard(tool_name, arguments, on_decision=on_decision)
        self.mount(card)
        self._maybe_scroll_to_bottom()
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
    """Base class for selectable messages with action buttons."""

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
        elif "btn-retry" in event.button.classes:
            self.post_message(RetryRequested(self, self.message_index))
        elif "btn-continue" in event.button.classes:
            self.post_message(ContinueRequested(self, self.message_index))
        elif "btn-fork" in event.button.classes:
            self.post_message(ForkRequested(self, self.message_index))


class UserMessage(SelectableMessage):
    """A user-authored message bubble."""

    def __init__(self, text: str, message_index: int | None = None) -> None:
        super().__init__(message_index=message_index)
        self._text = text
        self._await_mount: Any = None

    def __await__(self) -> Any:
        async def _wait() -> UserMessage:
            if self._await_mount is not None:
                await self._await_mount
            if self.parent and hasattr(self.parent, "_maybe_scroll_to_bottom"):
                self.parent._maybe_scroll_to_bottom()
            return self

        return _wait().__await__()

    def compose(self):  # type: ignore[override]
        yield Static("[bold cyan]You[/bold cyan]")
        yield Static(self._text)
        with Horizontal(classes="message-actions"):
            yield Button("⏪ Rewind", classes="btn-action btn-rewind")
            yield Button("🔄 Retry", classes="btn-action btn-retry")
            yield Button("🍴 Fork", classes="btn-action btn-fork")


import re

_CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)```", re.DOTALL)


class AssistantMessage(SelectableMessage):
    """An assistant response rendered as Markdown with folded code blocks and long text."""

    def __init__(
        self,
        content: str,
        message_index: int | None = None,
        can_continue: bool = False,
    ) -> None:
        super().__init__(message_index=message_index)
        self._content = content
        self._can_continue = can_continue or _is_max_iterations_content(content)

    def compose(self):  # type: ignore[override]
        yield Static("[bold green]Agent[/bold green]")
        yield from self._compose_content()
        with Horizontal(classes="message-actions"):
            yield Button("⏪ Rewind", classes="btn-action btn-rewind")
            yield Button("🔄 Retry", classes="btn-action btn-retry")
            if self._can_continue:
                yield Button("▶ Continue", classes="btn-action btn-continue")
            yield Button("🍴 Fork", classes="btn-action btn-fork")

    def _compose_content(self):
        """Yield markdown or collapsible widgets for code blocks and large text paragraphs."""
        segments = _split_markdown_segments(self._content)
        if not segments:
            yield Markdown(self._content)
            return

        for seg_type, text, lang in segments:
            if seg_type == "code":
                lines = text.strip().splitlines()
                # Fold code blocks with >= 4 lines
                if len(lines) >= 4:
                    title = f"📦 Code ({lang or 'code'}, {len(lines)} lines)"
                    yield Collapsible(
                        Markdown(f"```{lang}\n{text}\n```"),
                        title=title,
                        collapsed=True,
                        classes="content-collapse",
                    )
                else:
                    yield Markdown(f"```{lang}\n{text}\n```")
            else:
                lines = [l for l in text.strip().splitlines() if l.strip()]
                # Fold large text paragraphs (>= 8 lines or >= 400 chars)
                if len(lines) >= 8 or len(text.strip()) >= 400:
                    summary = lines[0][:40].strip() if lines else "Text"
                    title = f"📄 Text ({len(lines)} lines) — {summary}…"
                    yield Collapsible(
                        Markdown(text.strip()),
                        title=title,
                        collapsed=True,
                        classes="content-collapse",
                    )
                else:
                    yield Markdown(text)


def _is_max_iterations_content(content: str) -> bool:
    """Check if content indicates conversation reached max iteration limit."""
    kw = ("exceeded", "within", "unable to complete the task within", "最大轮数", "最大迭代", "达到最大")
    return any(k in content for k in kw) and ("step" in content or "iteration" in content or "轮" in content)


def _split_markdown_segments(content: str) -> list[tuple[str, str, str]]:
    """Split markdown into text and code segments: (type, text, lang)."""
    segments: list[tuple[str, str, str]] = []
    last_end = 0
    for match in _CODE_BLOCK_RE.finditer(content):
        start, end = match.span()
        if start > last_end:
            text_part = content[last_end:start]
            if text_part.strip():
                segments.append(("text", text_part, ""))
        lang = match.group(1).strip()
        code = match.group(2)
        segments.append(("code", code, lang))
        last_end = end
    if last_end < len(content):
        text_part = content[last_end:]
        if text_part.strip():
            segments.append(("text", text_part, ""))
    return segments


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
