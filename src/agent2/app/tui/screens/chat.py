"""Main chat screen — composes message list, input area, and status bar."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

from agent2.llm.message import Role
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import MessageList
from agent2.app.tui.widgets.status_bar import StatusBar

if TYPE_CHECKING:
    from agent2.app.tui.app import Agent2App


# ── Slash command definitions ───────────────────────────────────

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/model", "Switch LLM model"),
    ("/models", "Alias for /model"),
    ("/clear", "Clear display"),
    ("/new", "Start new session"),
    ("/resume", "Resume saved session"),
    ("/help", "Show help"),
    ("/h", "Alias for /help"),
    ("/exit", "Exit application"),
    ("/quit", "Alias for /exit"),
]


# ── TUI-logger events (posted by TUILogger → handled here) ─────


class ThoughtReceived(Message):
    def __init__(self, content: str, step: int) -> None:
        super().__init__()
        self.content = content
        self.step = step


class ToolCallStarted(Message):
    def __init__(self, tool_name: str, arguments: dict) -> None:  # type: ignore[type-arg]
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments


class ToolCallCompleted(Message):
    def __init__(self, content: str, is_error: bool) -> None:
        super().__init__()
        self.content = content
        self.is_error = is_error


# ── ChatScreen ──────────────────────────────────────────────────


class ChatScreen(Screen):
    """Primary screen: status bar + message list + input area."""

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
        Binding("ctrl+d", "quit_app", "Quit", priority=True),
    ]

    def compose(self):  # type: ignore[override]
        yield StatusBar()
        yield MessageList(id="messages")
        with Vertical(id="input-area"):
            yield OptionList(id="completion-list")
            yield Static(
                "Enter ↵ send  │  Shift+Enter ↵ newline  │  Ctrl+D quit",
                id="input-hint",
            )
            yield ChatInput(id="chat-input")

    def on_mount(self) -> None:
        self.query_one("#chat-input", ChatInput).focus()
        app: Agent2App = self.app  # type: ignore[assignment]
        self.query_one(StatusBar).model_name = app.agent.llm.model
        self._current_tool_card = None
        self._thought_start: float | None = None

        # Auto-send initial message if provided via -i
        if app.initial_message:
            msg = app.initial_message
            app.initial_message = None  # consume
            self.query_one("#messages", MessageList).add_user_message(msg)
            self._run_agent(_process_context(msg))

    # ── Input handling ──────────────────────────────────────────

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.text
        self._hide_completion()

        if text.startswith("/"):
            self._handle_command(text)
            return

        processed = _process_context(text)
        self.query_one("#messages", MessageList).add_user_message(text)
        self._run_agent(processed)

    # ── Completion ──────────────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Show / update / hide the completion list as the user types."""
        text = event.text_area.text
        # Show completions only when text starts with / and has no space yet
        if text.startswith("/") and " " not in text:
            prefix = text.lower()
            matches = [
                (cmd, desc)
                for cmd, desc in SLASH_COMMANDS
                if cmd.startswith(prefix)
            ]
            if matches:
                self._show_completion(matches)
                return
        self._hide_completion()

    def on_chat_input_completion_key(self, event: ChatInput.CompletionKey) -> None:
        """Handle navigation keys forwarded from ChatInput."""
        completion = self.query_one("#completion-list", OptionList)
        if event.key == "tab":
            self._accept_completion()
        elif event.key == "down":
            h = completion.highlighted
            if h is None:
                completion.highlighted = 0
            elif h < completion.option_count - 1:
                completion.highlighted = h + 1
        elif event.key == "up":
            h = completion.highlighted
            if h is not None and h > 0:
                completion.highlighted = h - 1
        elif event.key == "escape":
            self._hide_completion()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle click / Enter on a completion item."""
        option_id = event.option.id
        if option_id:
            self._accept_completion(str(option_id))

    def _show_completion(self, matches: list[tuple[str, str]]) -> None:
        completion = self.query_one("#completion-list", OptionList)
        completion.clear_options()
        for cmd, desc in matches:
            completion.add_option(Option(f"{cmd}  [dim]{desc}[/dim]", id=cmd))
        completion.highlighted = 0
        completion.add_class("visible")
        self.query_one("#chat-input", ChatInput).show_completion = True

    def _hide_completion(self) -> None:
        completion = self.query_one("#completion-list", OptionList)
        completion.remove_class("visible")
        self.query_one("#chat-input", ChatInput).show_completion = False

    def _accept_completion(self, cmd: str | None = None) -> None:
        if cmd is None:
            completion = self.query_one("#completion-list", OptionList)
            h = completion.highlighted
            if h is not None:
                option = completion.get_option_at_index(h)
                cmd = str(option.id) if option.id else None
        if cmd:
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.clear()
            chat_input.insert(cmd + " ")
        self._hide_completion()

    # ── Agent worker ────────────────────────────────────────────

    @work(exclusive=True, group="agent")
    async def _run_agent(self, text: str) -> None:
        from agent2.app.tui.app import TUILogger

        app: Agent2App = self.app  # type: ignore[assignment]
        agent = app.agent
        messages = self.query_one("#messages", MessageList)

        original_log = agent.log
        agent.log = TUILogger(agent.name, screen=self)
        agent.approval_callback = self._request_approval  # type: ignore[attr-defined]
        self._thought_start = time.monotonic()

        try:
            result = await agent.chat(text)
            messages.add_assistant_message(result)
            self._update_token_count()
        except asyncio.CancelledError:
            messages.add_system_message("⛔ Interrupted by user.")
        except Exception as exc:
            messages.add_system_message(f"❌ Error: {exc}")
        finally:
            agent.log = original_log

        # Auto-save
        app.session_manager.save(app.session_id, agent.to_dict())

    # ── HITL approval via Future ────────────────────────────────

    async def _request_approval(self, tool_call) -> str:  # type: ignore[type-arg]
        from agent2.app.tui.widgets.confirm_modal import ConfirmModal

        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        def on_result(result: str) -> None:
            if not future.done():
                future.set_result(result or "reject")

        self.app.push_screen(
            ConfirmModal(tool_call.name, tool_call.arguments),
            callback=on_result,
        )
        return await future

    # ── TUI-logger event handlers ───────────────────────────────

    def on_thought_received(self, event: ThoughtReceived) -> None:
        elapsed = time.monotonic() - (self._thought_start or time.monotonic())
        messages = self.query_one("#messages", MessageList)
        messages.add_thinking_block(event.content, event.step, elapsed)

    def on_tool_call_started(self, event: ToolCallStarted) -> None:
        messages = self.query_one("#messages", MessageList)
        self._current_tool_card = messages.add_tool_card(
            event.tool_name,
            event.arguments,
        )

    def on_tool_call_completed(self, event: ToolCallCompleted) -> None:
        if self._current_tool_card is not None:
            self._current_tool_card.set_result(
                event.content, is_error=event.is_error,
            )
            self._current_tool_card = None

    # ── Slash commands ──────────────────────────────────────────

    def _handle_command(self, text: str) -> None:
        from agent2.app.tui.screens.model_select import ModelSelectScreen

        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else None
        messages = self.query_one("#messages", MessageList)
        app: Agent2App = self.app  # type: ignore[assignment]

        if cmd in ("/model", "/models"):
            if arg:
                app.switch_model(arg)
                self.query_one(StatusBar).model_name = app.agent.llm.model
                messages.add_system_message(
                    f"Model switched → {app.agent.llm.model}"
                )
            else:
                def on_model(name: str) -> None:
                    if name:
                        app.switch_model(name)
                        self.query_one(StatusBar).model_name = app.agent.llm.model
                        messages.add_system_message(
                            f"Model switched → {app.agent.llm.model}"
                        )
                self.app.push_screen(ModelSelectScreen(), callback=on_model)

        elif cmd == "/clear":
            messages.clear_messages()
            messages.add_system_message("🧹 Display cleared.")

        elif cmd == "/new":
            app.session_manager.save(app.session_id, app.agent.to_dict())
            app.agent.reset()
            app.new_session_id()
            messages.clear_messages()
            messages.add_system_message("✨ New session started.")

        elif cmd == "/resume":
            self._handle_resume(arg)

        elif cmd in ("/help", "/h"):
            messages.add_system_message(
                "[bold cyan]Commands[/bold cyan]\n"
                "  /model [name]   Switch model\n"
                "  /clear          Clear display\n"
                "  /new            New session\n"
                "  /resume [id]    Resume session\n"
                "  /help           This help\n"
                "  /exit           Quit\n"
                "\n[bold cyan]Context Injection[/bold cyan]\n"
                "  #file <path>    Inject file content\n"
                "  #dir  <path>    Inject directory listing"
            )

        elif cmd in ("/exit", "/quit"):
            app.session_manager.save(app.session_id, app.agent.to_dict())
            self.app.exit()

        else:
            messages.add_system_message(
                f"Unknown command: {cmd}.  Type /help for help."
            )

    def _handle_resume(self, arg: str | None) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        sessions = app.session_manager.list_sessions()

        if arg:
            match = next(
                (s for s in sessions if s["id"].startswith(arg)), None,
            )
            if match:
                app.load_session(match["id"])
                messages.clear_messages()
                self._rebuild_messages()
                self.query_one(StatusBar).model_name = app.agent.llm.model
                messages.add_system_message(
                    f"🔄 Session {match['id'][:8]} restored."
                )
            else:
                messages.add_system_message(f"Session matching '{arg}' not found.")
            return

        if not sessions:
            messages.add_system_message("No saved sessions.")
            return

        listing = "\n".join(
            f"  {s['id'][:8]}  {s['title'] or '(untitled)'}"
            for s in sessions[:10]
        )
        messages.add_system_message(
            f"[bold]Recent sessions:[/bold]\n{listing}\n\n"
            "Use  /resume <id-prefix>  to restore."
        )

    def _rebuild_messages(self) -> None:
        """Re-populate the message list from the agent's history."""
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        for msg in app.agent.messages:
            if msg.role == Role.USER:
                messages.add_user_message(msg.content or "")
            elif msg.role == Role.ASSISTANT:
                messages.add_assistant_message(msg.content or "")

    # ── Interrupt / Quit ────────────────────────────────────────

    def action_interrupt(self) -> None:
        """Ctrl+C: cancel the running agent worker (does not exit)."""
        for w in self.app.workers:
            if w.group == "agent" and w.is_running:
                w.cancel()
                return

    def action_quit_app(self) -> None:
        """Ctrl+D: save session and exit."""
        app: Agent2App = self.app  # type: ignore[assignment]
        app.session_manager.save(app.session_id, app.agent.to_dict())
        self.app.exit()

    # ── Helpers ─────────────────────────────────────────────────

    def _update_token_count(self) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        usage = getattr(app.agent, "_last_usage", None)
        if usage:
            self.query_one(StatusBar).token_count = usage.total_tokens


# ── Context injection ───────────────────────────────────────────


def _process_context(text: str) -> str:
    """Expand ``#file <path>`` and ``#dir <path>`` into inline context."""

    def _read_file(m: re.Match[str]) -> str:
        p = Path(m.group(1)).expanduser()
        try:
            content = p.read_text(encoding="utf-8")
            return f'\n<file path="{p}">\n{content}\n</file>\n'
        except Exception as exc:
            return f"\n[Error reading {p}: {exc}]\n"

    def _read_dir(m: re.Match[str]) -> str:
        p = Path(m.group(1)).expanduser()
        try:
            entries = sorted(p.iterdir())
            listing = "\n".join(
                f"{'[dir]' if e.is_dir() else '[file]'} {e.name}"
                for e in entries
            )
            return f'\n<directory path="{p}">\n{listing}\n</directory>\n'
        except Exception as exc:
            return f"\n[Error reading dir {p}: {exc}]\n"

    text = re.sub(r"#file\s+(\S+)", _read_file, text)
    text = re.sub(r"#dir\s+(\S+)", _read_dir, text)
    return text
