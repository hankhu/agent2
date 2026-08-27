"""Multi-line chat input with Enter-to-submit / Shift+Enter-for-newline.

Also supports completion navigation: when ``show_completion`` is ``True``,
Tab / Up / Down / Escape are forwarded to the parent screen via
:class:`CompletionKey` messages instead of being handled by the TextArea.
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import TextArea


class ChatInput(TextArea):
    """Text input area for composing messages.

    * **Enter** submits the current text.
    * **Shift+Enter** inserts a newline.
    * Pasting multi-line text does *not* trigger a submit.
    * When :attr:`show_completion` is ``True``, navigation keys are
      forwarded via :class:`CompletionKey` messages.
    """

    show_completion: reactive[bool] = reactive(False)

    class Submitted(Message):
        """Posted when the user presses Enter with non-empty text."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class CompletionKey(Message):
        """Forwarded navigation key while the completion list is visible."""

        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(
            language="markdown",
            show_line_numbers=False,
            soft_wrap=True,
            **kwargs,
        )
        self._history: list[str] = []
        self._history_index: int | None = None
        self._draft = ""

    # Override internal key handler so we intercept *before* TextArea acts.
    async def _on_key(self, event: events.Key) -> None:
        # ── Ctrl+D: quit (saves the session via ChatScreen) ────
        if event.key == "ctrl+d":
            quit_action = getattr(self.screen, "action_quit_app", None)
            if quit_action is not None:
                quit_action()
                event.prevent_default()
                event.stop()
                return

        # ── Completion navigation ───────────────────────────────
        if self.show_completion and event.key in ("tab", "up", "down", "escape"):
            self.post_message(self.CompletionKey(event.key))
            event.prevent_default()
            event.stop()
            return

        # ── History navigation (Up/Down) ───────────────────────
        if not self.show_completion and event.key == "up" and self._history:
            if self._history_index is None:
                self._draft = self.text
                self._history_index = len(self._history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            self.text = self._history[self._history_index]
            event.prevent_default()
            event.stop()
            return

        if not self.show_completion and event.key == "down" and self._history_index is not None:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.text = self._history[self._history_index]
            else:
                self._history_index = None
                self.text = self._draft
            event.prevent_default()
            event.stop()
            return

        # ── Enter to submit (Shift+Enter falls through for newline) ─
        if event.key == "enter":
            text = self.text.strip()
            if text:
                if not text.startswith("/") and (not self._history or self._history[-1] != text):
                    self._history.append(text)
                self._history_index = None
                self._draft = ""
                self.post_message(self.Submitted(text))
                self.clear()
            event.prevent_default()
            event.stop()
            return

        # ── Default TextArea handling for everything else ───────
        await super()._on_key(event)
