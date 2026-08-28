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

from agent2.llm.message import Role, Usage
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
    ("/sessions", "List & manage sessions (resume/rename/delete)"),
    ("/session", "Alias for /sessions"),
    ("/rename", "Rename current session"),
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


class StatusText(Message):
    """Update the status bar's processing label (e.g. "Running shell_exec…")."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


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
        self._current_tool_card = None
        self._thought_start: float | None = None
        self._run_generation = 0
        self._sync_status_bar()

        # Auto-send initial message if provided via -i
        if app.initial_message:
            msg = app.initial_message
            app.initial_message = None  # consume
            self.query_one("#messages", MessageList).add_user_message(msg)
            self._run_agent(msg)

    # ── Input handling ──────────────────────────────────────────

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.text
        self._hide_completion()

        if text.startswith("/"):
            self._handle_command(text)
            return

        # Echo the user message into the chat window immediately, *before*
        # any (potentially slow) context expansion or LLM request.
        self.query_one("#messages", MessageList).add_user_message(text)
        self._run_agent(text)

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
        if event.key in ("tab", "enter"):
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
        status = self.query_one(StatusBar)

        original_log = agent.log
        agent.log = TUILogger(agent.name, screen=self)
        agent.approval_callback = self._request_approval  # type: ignore[attr-defined]
        self._thought_start = time.monotonic()

        # Generation counter: if this worker is cancelled by a newer run
        # (exclusive worker), the stale finally-block must not clear the
        # busy state that the newer run just set.
        self._run_generation += 1
        generation = self._run_generation

        # Show "Processing…" in the status bar right away, until the
        # response returns (or the request fails / is interrupted).
        status.busy = True
        status.status_text = "Processing…"

        try:
            # Expand #file / #dir context inside the worker so slow disk
            # reads don't delay the user message from appearing.
            processed = await asyncio.to_thread(_process_context, text)
            result = await agent.chat(processed)
            messages.add_assistant_message(result)
            self._sync_status_bar()
        except asyncio.CancelledError:
            messages.add_system_message("⛔ Interrupted by user.")
        except Exception as exc:
            messages.add_system_message(f"❌ Error: {exc}")
        finally:
            agent.log = original_log
            if generation == self._run_generation:
                status.busy = False
                status.status_text = ""

        # Auto-save (skipped when the conversation has no input at all)
        self._save_session()

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
        self.query_one(StatusBar).status_text = "Processing…"

    def on_status_text(self, event: StatusText) -> None:
        self.query_one(StatusBar).status_text = event.text

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
                self._sync_status_bar()
                messages.add_system_message(
                    f"Model switched → {app.agent.llm.model}"
                )
            else:
                def on_model(name: str) -> None:
                    if name:
                        app.switch_model(name)
                        self._sync_status_bar()
                        messages.add_system_message(
                            f"Model switched → {app.agent.llm.model}"
                        )
                self.app.push_screen(ModelSelectScreen(), callback=on_model)

        elif cmd == "/clear":
            messages.clear_messages()
            messages.add_system_message("🧹 Display cleared.")

        elif cmd == "/new":
            self._save_session()
            app.agent.reset()
            app.new_session_id()
            messages.clear_messages()
            self._reset_usage()
            self.query_one(StatusBar).reset_timer()
            self._sync_status_bar()
            messages.add_system_message("✨ New session started.")

        elif cmd in ("/resume", "/sessions", "/session"):
            self._handle_resume(arg)

        elif cmd == "/rename":
            if not arg:
                curr = f" (current: [bold]{app.session_title}[/bold])" if app.session_title else ""
                messages.add_system_message(f"Usage: /rename <new-title>{curr}")
                return
            if not self._session_has_input():
                messages.add_system_message("当前会话还没有内容，暂不保存，无法重命名。")
                return
            app.session_title = arg.strip()
            app.session_manager.save(
                app.session_id,
                app.agent.to_dict(),
                title=app.session_title,
            )
            messages.add_system_message(
                f"✏️ Session renamed to: [bold cyan]{app.session_title}[/bold cyan]"
            )

        elif cmd in ("/help", "/h"):
            messages.add_system_message(
                "[bold cyan]Commands[/bold cyan]\n"
                "  /model [name]   Switch model\n"
                "  /clear          Clear display\n"
                "  /new            New session\n"
                "  /sessions       List & manage sessions (resume/rename/delete)\n"
                "  /resume [id]    Resume session\n"
                "  /rename <title> Rename current session\n"
                "  /help           This help\n"
                "  /exit           Quit\n"
                "\n[bold cyan]Context Injection[/bold cyan]\n"
                "  #file <path>    Inject file content\n"
                "  #dir  <path>    Inject directory listing"
            )

        elif cmd in ("/exit", "/quit"):
            if self._session_has_input():
                app.session_manager.save(
                    app.session_id,
                    app.agent.to_dict(),
                    title=app.session_title or "",
                )
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
                self._reset_usage()
                self.query_one(StatusBar).reset_timer()
                self._sync_status_bar()
                messages.add_system_message(
                    f"🔄 Session {match['id'][:8]} restored."
                )
            else:
                messages.add_system_message(f"Session matching '{arg}' not found.")
            return

        if not sessions:
            messages.add_system_message("No saved sessions.")
            return

        from agent2.app.tui.screens.session_select import SessionSelectScreen

        def on_session(session_id: str | None) -> None:
            if not session_id:
                return
            app.load_session(session_id)
            messages.clear_messages()
            self._rebuild_messages()
            self._reset_usage()
            self.query_one(StatusBar).reset_timer()
            self._sync_status_bar()
            messages.add_system_message(
                f"🔄 Session {session_id[:8]} restored."
            )

        self.app.push_screen(
            SessionSelectScreen(sessions, session_manager=app.session_manager),
            callback=on_session,
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
        """Ctrl+D: save the session (unless empty) and exit."""
        app: Agent2App = self.app  # type: ignore[assignment]
        if self._session_has_input():
            app.session_manager.save(
                app.session_id,
                app.agent.to_dict(),
                title=app.session_title or "",
            )
        self.app.exit()


    # ── Helpers ─────────────────────────────────────────────────

    def _session_has_input(self) -> bool:
        """Whether the current conversation contains at least one user message."""
        app: Agent2App = self.app  # type: ignore[assignment]
        return any(m.role == Role.USER for m in app.agent.messages)

    def _save_session(self) -> None:
        """Persist the current session, skipping empty (no-input) conversations.

        An empty session — nothing but the system prompt, e.g. the app was
        opened and quit without sending a message — must not create a record.
        """
        app: Agent2App = self.app  # type: ignore[assignment]
        if not self._session_has_input():
            return
        app.session_manager.save(app.session_id, app.agent.to_dict())

    def _reset_usage(self) -> None:
        """Zero the LLM usage counters and the status bar token readouts.

        Called when the current conversation changes (``/new``, ``/resume``):
        restored sessions have no persisted usage, so showing the previous
        conversation's totals would be misleading.
        """
        app: Agent2App = self.app  # type: ignore[assignment]
        llm = app.agent.llm
        llm.total_usage = Usage()
        llm.last_usage = None
        status = self.query_one(StatusBar)
        status.input_tokens = 0
        status.output_tokens = 0
        status.context_tokens = 0

    def _sync_status_bar(self) -> None:
        """Push model name and token usage from the agent's LLM to the bar."""
        app: Agent2App = self.app  # type: ignore[assignment]
        status = self.query_one(StatusBar)
        llm = app.agent.llm

        status.model_name = llm.model
        status.context_window = getattr(llm, "context_window", 0) or 0

        total = getattr(llm, "total_usage", None)
        if total is not None:
            status.input_tokens = total.prompt_tokens
            status.output_tokens = total.completion_tokens

        # Current context size = prompt tokens of the most recent request
        # (the prompt of the last call contains the whole conversation).
        last = getattr(llm, "last_usage", None)
        if last is not None and last.prompt_tokens:
            status.context_tokens = last.prompt_tokens


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
