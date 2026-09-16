"""Main chat screen — composes message list, input area, and status bar."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import work
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import OptionList, TextArea
from textual.widgets.option_list import Option

from agent2.llm.message import Message as LLMMessage, Role, Usage
from agent2.app.tui.planner import (
    Plan,
    format_plan_markdown,
    generate_plan,
    is_plan_confirmation,
    synthesize_plan_results,
    topological_sort_tasks,
)
from agent2.app.tui.screens.session_select import SessionSelectScreen
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import (
    AssistantMessage,
    ContinueRequested,
    ForkRequested,
    MessageList,
    RetryRequested,
    RewindRequested,
    UserMessage,
)
from agent2.app.tui.widgets.nav_bar import TopTabBar
from agent2.app.tui.widgets.shortcut_help import ShortcutHelp
from agent2.app.tui.widgets.status_bar import (
    LONG_OPERATION_SECONDS,
    ContextBar,
    StatusBar,
    _fmt_clock,
    _fmt_operation_duration,
)
from agent2.app.tui.widgets.welcome_banner import WelcomeBanner

if TYPE_CHECKING:
    from agent2.app.tui.app import Agent2App


# ── Slash command definitions ───────────────────────────────────

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/plan", "Plan mode: analyze intent, break down tasks, confirm and execute"),
    ("/ask", "Ask mode: read-only Q&A, write & execute disabled"),
    ("/agent", "Agent mode (default): full ReAct agent with tools"),
    ("/model", "Switch LLM model"),
    ("/models", "Alias for /model"),
    ("/skills", "List available skills (use /<skill_name> to invoke)"),
    ("/tools", "List currently active tools and descriptions"),
    ("/mcp", "Manage MCP servers: list, enable, disable (/mcp [list|enable|disable])"),
    ("/cfg", "Open configuration (~/.config/agent2/config.json) in system editor"),
    ("/config", "Alias for /cfg"),
    ("/clear", "Clear display"),
    ("/compact", "Compact conversation context to free window capacity (/compact [keep_turns])"),
    ("/retry", "Retry last user query / regenerate response"),
    ("/continue", "Continue execution if paused or reached max iterations"),
    ("/rewind", "Rewind to previous conversation round"),
    ("/fork", "Fork current session and continue (/fork [title])"),
    ("/new", "Start new session"),
    ("/resume", "Resume saved session"),
    ("/sessions", "List & manage sessions (resume/rename/delete)"),
    ("/session", "Alias for /sessions"),
    ("/rename", "Rename current session"),
    ("/export", "Export conversation (/export [path])"),
    ("/yolo", "YOLO / Autopilot mode: auto-approve operations & autonomous decisions (/yolo [on|off|show])"),
    ("/autopilot", "Alias for /yolo"),
    ("/allow-all", "Allow-all mode: auto-approve all operations (/allow-all [on|off|show])"),
    ("/help", "Show help"),
    ("/h", "Alias for /help"),
    ("/exit", "Exit application"),
    ("/quit", "Alias for /exit"),
]


def get_all_commands(context: Any | None = None) -> list[tuple[str, str]]:
    """Return all slash commands combined with available skill commands."""
    from agent2.context import discover_skills

    commands = list(SLASH_COMMANDS)
    skills = getattr(context, "skills", None) if context else None
    if skills is None:
        skills = discover_skills()

    seen_cmds = {cmd for cmd, _ in commands}
    for s in skills:
        cmd = f"/{s.name}"
        if cmd not in seen_cmds:
            desc = f"[Skill] {s.description[:60]}" if s.description else "[Skill]"
            commands.append((cmd, desc))
            seen_cmds.add(cmd)
    return commands




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


def _is_waiting_for_input(text: str | None) -> bool:
    """Check if the assistant response is asking a question or waiting for user input."""
    if not text:
        return False
    stripped = text.strip()
    clean = stripped.rstrip("*_`~ ")
    if clean.endswith(("?", "？")):
        return True
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if lines:
        last_clean = lines[-1].rstrip("*_`~ ")
        if last_clean.endswith(("?", "？")):
            return True
    return False


# ── ChatScreen ──────────────────────────────────────────────────


class ChatScreen(Screen):
    """Primary screen: top nav bar + message list + input area + context & status bars."""

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
        Binding("ctrl+o", "toggle_tool_results", "Toggle Results", priority=True),
        Binding("ctrl+d", "quit_app", "Quit", priority=True),
        Binding("tab", "cycle_tab_next", "Next Tab", priority=False, show=False),
        Binding("shift+tab", "cycle_tab_prev", "Previous Tab", priority=False, show=False),
        Binding("escape", "cancel_selection", "Cancel Selection", priority=False),
        Binding("question_mark", "toggle_shortcuts", "Shortcuts", show=False),
        Binding("plus", "open_sessions_shortcut", "Sessions", show=False),
        Binding("f1", "tab_current", "Current Tab", show=False),
        Binding("f2", "tab_sessions", "Sessions Tab", show=False),
        Binding("f3", "tab_skills", "Skills Tab", show=False),
    ]

    def compose(self):  # type: ignore[override]
        yield TopTabBar(id="top-nav")
        yield MessageList(id="messages")
        with Vertical(id="input-area"):
            yield ContextBar(id="context-bar")
            yield OptionList(id="completion-list")
            yield ShortcutHelp()
            yield ChatInput(id="chat-input")
        yield StatusBar()

    def on_mount(self) -> None:
        try:
            self.query_one(StatusBar).active_tab = "current"
        except Exception:
            pass
        try:
            self.query_one("#tab-current").focus()
        except Exception:
            self.query_one("#chat-input", ChatInput).focus()
        app: Agent2App = self.app  # type: ignore[assignment]
        self._current_tool_card = None
        self._current_tool_name: str | None = None
        self._current_tool_started_at: float | None = None
        self._current_tool_start_monotonic: float | None = None
        self._thought_start: float | None = None
        self._run_generation = 0
        self._pending_plan: Plan | None = None
        self._plan_goal: str = ""
        self._tps_estimate: float = 0.0
        self._last_long_operation_started_at: float = 0.0
        self._sync_status_bar()

        # If starting or resuming a session with history, render messages
        if self._session_has_input():
            self._rebuild_messages()
        else:
            self.query_one("#messages", MessageList).mount(WelcomeBanner(id="welcome-banner"))

        # Proactively connect enabled MCP servers in Textual event loop
        self.run_worker(self._init_mcp_servers(), exclusive=False)

        # Auto-send initial message if provided via -i
        if app.initial_message:
            msg = app.initial_message
            app.initial_message = None  # consume
            self.query_one("#messages", MessageList).add_user_message(msg)
            self._run_agent(msg)

    async def _init_mcp_servers(self) -> None:
        """Connect enabled MCP servers inside Textual's active event loop."""
        import os

        # Skip connecting external MCP servers during automated testing unless explicitly enabled
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("AGENT2_TEST_MCP"):
            return

        from agent2.app.config import load_config
        from agent2.mcp import MCPManager, MCPServerConfig

        app: Agent2App = self.app  # type: ignore[assignment]
        manager: MCPManager | None = getattr(app, "mcp_manager", None)
        if manager is None:
            cfg = load_config()
            if cfg.mcp_servers:
                servers = {
                    k: MCPServerConfig.model_validate(v)
                    for k, v in cfg.mcp_servers.items()
                }
                manager = MCPManager(servers)
                app.mcp_manager = manager
                app.agent.mcp_manager = manager  # type: ignore[attr-defined]

        if not manager:
            return

        try:
            tools = await manager.connect()
            for t in tools:
                if t.name in app.agent.tool_registry:
                    app.agent.tool_registry.unregister(t.name)
                app.agent.tool_registry.register(t)
            if hasattr(app.agent, "_auto_approved"):
                app.agent._auto_approved.update(manager.always_allow_tools)
        except BaseException as exc:
            import logging

            logging.getLogger(__name__).warning("MCP background init error: %s", exc)

    def _on_screen_resume(self, event: events.ScreenResume) -> None:
        super()._on_screen_resume(event)
        self._set_active_tab("current")

    # ── Tab Navigation ──────────────────────────────────────────

    def _set_active_tab(self, tab_id: str) -> None:
        """Keep the top tab bar and the bottom shortcut hint in sync."""
        try:
            top_bar = self.query_one(TopTabBar)
            top_bar.active_tab = tab_id
            top_bar._update_tab_classes(tab_id)
        except Exception:
            pass
        try:
            self.query_one(StatusBar).active_tab = tab_id
        except Exception:
            pass
        if tab_id != "current":
            try:
                self.query_one(ShortcutHelp).hide_help()
            except Exception:
                pass
            try:
                self._hide_completion()
            except Exception:
                pass

    def on_chat_input_cycle_tab_requested(self, event: ChatInput.CycleTabRequested) -> None:
        if getattr(event, "direction", 1) == -1:
            self.action_cycle_tab_prev()
        else:
            self.action_cycle_tab_next()

    def on_chat_input_shortcuts_requested(self, event: ChatInput.ShortcutsRequested) -> None:
        self.action_toggle_shortcuts()

    def on_chat_input_sessions_requested(self, event: ChatInput.SessionsRequested) -> None:
        self.action_tab_sessions()

    def action_cycle_tab_next(self) -> None:
        """Tab: immediately switch to the next top-level panel."""
        try:
            self.query_one(TopTabBar).cycle_tab(1)
        except Exception:
            pass

    def action_cycle_tab_prev(self) -> None:
        """Shift+Tab: immediately switch to the previous top-level panel."""
        try:
            self.query_one(TopTabBar).cycle_tab(-1)
        except Exception:
            pass

    def action_toggle_shortcuts(self) -> None:
        """Show or hide the inline shortcut panel above the chat input."""
        try:
            shortcut_help = self.query_one(ShortcutHelp)
            showing = shortcut_help.toggle_help()
            if showing:
                self._hide_completion()
        except Exception:
            pass

    def action_open_sessions_shortcut(self) -> None:
        """Immediate ``+`` shortcut for the Sessions panel."""
        self.action_tab_sessions()

    def on_top_tab_bar_tab_selected(self, event: TopTabBar.TabSelected) -> None:
        tab_id = event.tab_id
        self._set_active_tab(tab_id)
        if tab_id == "current":
            self.query_one("#chat-input", ChatInput).focus()
        elif tab_id == "sessions":
            self._open_sessions_dialog()
        elif tab_id == "skills":
            self._open_skills_dialog()

    def action_tab_current(self) -> None:
        self._set_active_tab("current")
        self.query_one("#chat-input", ChatInput).focus()

    def action_tab_sessions(self) -> None:
        self._set_active_tab("sessions")
        self._open_sessions_dialog()

    def action_tab_skills(self) -> None:
        self._set_active_tab("skills")
        self._open_skills_dialog()

    def _open_sessions_dialog(self) -> None:
        self._set_active_tab("sessions")
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        try:
            sessions = app.session_manager.list_sessions()
        except Exception as exc:
            messages.add_system_message(f"❌ Failed to list sessions: {exc}")
            self._set_active_tab("current")
            self.query_one("#chat-input", ChatInput).focus()
            return

        if not sessions:
            messages.add_system_message("No saved sessions.")

        def on_session(session_id: str | None) -> None:
            self._set_active_tab("current")
            self.query_one("#chat-input", ChatInput).focus()
            if not session_id:
                return
            app.load_session(session_id)
            messages.clear_messages()
            self._rebuild_messages()
            self._reset_session_metrics()
            self._sync_status_bar()
            messages.add_system_message(
                f"🔄 Session {session_id[:8]} restored."
            )

        self.app.push_screen(
            SessionSelectScreen(sessions, session_manager=app.session_manager),
            callback=on_session,
        )

    def _open_skills_dialog(self) -> None:
        from agent2.app.tui.screens.skill_select import SkillSelectScreen
        from agent2.context import discover_skills

        self._set_active_tab("skills")
        app: Agent2App = self.app  # type: ignore[assignment]
        skills = discover_skills()
        if getattr(app, "context", None):
            app.context.skills = skills

        def on_skill(skill_name: str | None) -> None:
            self._set_active_tab("current")
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.focus()
            if skill_name:
                chat_input.value = f"/{skill_name} "
                chat_input.cursor_position = len(chat_input.value)

        self.app.push_screen(
            SkillSelectScreen(skills),
            callback=on_skill,
        )

    def _set_busy(self, busy: bool, text: str = "", state: str | None = None) -> None:
        """Update busy state and status text on both StatusBar and ContextBar."""
        effective_state = state if state is not None else ("busy" if busy else "idle")
        try:
            status = self.query_one(StatusBar)
            status.busy = busy
            status.status_text = text if busy else ""
            status.status_state = effective_state
        except Exception:
            pass
        try:
            ctx = self.query_one(ContextBar)
            ctx.busy = busy
            ctx.status_text = text if busy else ""
            ctx.status_state = effective_state
        except Exception:
            pass

    # ── Timing / throughput metrics ─────────────────────────────

    def _reset_session_metrics(self) -> None:
        """Reset session timer, TPS and long-operation readouts."""
        self._tps_estimate = 0.0
        self._last_long_operation_started_at = 0.0
        try:
            app: Agent2App = self.app  # type: ignore[assignment]
            llm = app.agent.llm
            llm.last_tps = None
            llm.last_request_duration = None
            llm.last_request_started_at = None
            llm.last_request_finished_at = None
            llm._request_started_monotonic = None
        except Exception:
            pass
        for widget_type in (StatusBar, ContextBar):
            try:
                widget = self.query_one(widget_type)
                widget.reset_timer()
                widget.tps = 0.0
                widget.long_operation = ""
            except Exception:
                pass

    def _record_long_operation(
        self,
        name: str,
        duration: float | None,
        started_at: float | None = None,
    ) -> None:
        """Remember a slow operation's duration and wall-clock start time."""
        if duration is None or duration < LONG_OPERATION_SECONDS:
            return
        if started_at is None:
            started_at = time.time() - duration
        if started_at < self._last_long_operation_started_at:
            return
        from rich.markup import escape

        self._last_long_operation_started_at = started_at
        text = (
            f"{escape(name)} {_fmt_operation_duration(duration)} "
            f"(started {_fmt_clock(started_at)})"
        )
        for widget_type in (ContextBar, StatusBar):
            try:
                self.query_one(widget_type).long_operation = text
            except Exception:
                pass

    def _update_tps_from_run(
        self,
        started_monotonic: float,
        base_completion_tokens: int = 0,
    ) -> None:
        """Estimate tokens-per-second for a completed agent run.

        Prefers the provider-level timing recorded by :class:`BaseLLM`; falls
        back to completion-token delta divided by wall time when a custom / test
        LLM does not expose timing metadata.
        """
        app: Agent2App = self.app  # type: ignore[assignment]
        llm = app.agent.llm
        duration = max(time.monotonic() - started_monotonic, 1e-9)
        provider_tps = getattr(llm, "last_tps", None)
        if provider_tps is not None and provider_tps > 0:
            self._tps_estimate = float(provider_tps)
        else:
            total = getattr(llm, "total_usage", None)
            completion = getattr(total, "completion_tokens", 0) if total else 0
            delta = max(0, completion - base_completion_tokens)
            self._tps_estimate = delta / duration if delta else 0.0

    def _resolve_tps(self) -> float:
        app: Agent2App = self.app  # type: ignore[assignment]
        llm = app.agent.llm
        provider_tps = getattr(llm, "last_tps", None)
        if provider_tps is not None and provider_tps > 0:
            return float(provider_tps)
        return max(0.0, float(getattr(self, "_tps_estimate", 0.0) or 0.0))

    def _switch_mode(self, new_mode: str) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        app.set_mode(new_mode)
        self._sync_status_bar()

    # ── Input handling ──────────────────────────────────────────

    async def _mount_and_render_user_message(
        self, text: str, message_index: int | None = None
    ) -> UserMessage:
        """Immediately mount user message into the chat dialog and render before network requests."""
        messages = self.query_one("#messages", MessageList)
        user_msg = messages.add_user_message(text, message_index=message_index)
        await user_msg
        messages._maybe_scroll_to_bottom()
        self.refresh(layout=True)
        if hasattr(self, "_compositor_refresh"):
            self._compositor_refresh()
        return user_msg

    async def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.text.strip()
        self._hide_completion()
        messages = self.query_one("#messages", MessageList)
        messages.deselect_all()

        # Shortcuts corresponding to bottom bar hints
        if text in ("?", "？", "help"):
            self.action_toggle_shortcuts()
            return

        if text in ("+", "＋"):
            self.action_tab_sessions()
            return

        if text.startswith("/"):
            await self._handle_command(text)
            return

        app: Agent2App = self.app  # type: ignore[assignment]
        if not app.agent._messages and app.agent.system_prompt:
            app.agent._messages.append(LLMMessage.system(app.agent.system_prompt))
        user_idx = len(app.agent._messages)

        await self._mount_and_render_user_message(text, message_index=user_idx)

        if getattr(app, "mode", "agent") == "plan":
            if self._pending_plan and is_plan_confirmation(text):
                plan = self._pending_plan
                goal = self._plan_goal or plan.goal
                self._pending_plan = None
                self._plan_goal = ""
                self._switch_mode("agent")
                messages.add_system_message(
                    "✅ 计划已确认，已退出 Plan 模式并进入 Agent 模式，开始派发子任务执行..."
                )
                self._run_plan_execution(plan, goal)
            else:
                self._run_plan_generation(text)
        else:
            # agent or ask mode
            self._run_agent(text)


    # ── Completion ──────────────────────────────────────────────

    def _get_completions(self) -> list[tuple[str, str]]:
        app: Agent2App = self.app  # type: ignore[assignment]
        ctx = getattr(app, "context", None)
        return get_all_commands(ctx)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Show / update / hide the completion list as the user types."""
        chat_input = self.query_one("#chat-input", ChatInput)
        if getattr(chat_input, "_history_index", None) is not None:
            self._hide_completion()
            return
        text = event.text_area.text
        if text:
            try:
                shortcut_help = self.query_one(ShortcutHelp)
                if shortcut_help.visible:
                    shortcut_help.hide_help()
            except Exception:
                pass

        # 1. Check for @file completion at cursor
        cursor_loc = event.text_area.cursor_location
        lines = text.splitlines()
        row = cursor_loc[0] if cursor_loc else 0
        col = cursor_loc[1] if cursor_loc else 0
        current_line = lines[row] if row < len(lines) else ""
        current_prefix = current_line[:col]

        at_match = re.search(r'(?:^|\s)@([^\s@]*)$', current_prefix)
        if at_match:
            from agent2.app.tui.file_completion import get_file_completions

            file_query = at_match.group(1)
            file_matches = get_file_completions(file_query)
            if file_matches:
                self._completion_mode = "file"
                self._show_completion(file_matches)
                return

        # 2. Show completions when text starts with / and has no space yet
        if text.startswith("/") and " " not in text:
            prefix = text.lower()
            all_commands = self._get_completions()
            matches = [
                (cmd, desc)
                for cmd, desc in all_commands
                if cmd.lower().startswith(prefix)
            ]
            if matches:
                self._completion_mode = "command"
                self._show_completion(matches)
                return

        self._hide_completion()

    def on_chat_input_completion_key(self, event: ChatInput.CompletionKey) -> None:
        """Handle navigation keys forwarded from ChatInput."""
        completion = self.query_one("#completion-list", OptionList)
        if event.key == "enter":
            self._accept_completion()
        elif event.key == "tab":
            if completion.option_count == 1:
                self._accept_completion()
            elif completion.option_count > 1:
                h = completion.highlighted
                if h is None:
                    completion.highlighted = 0
                else:
                    completion.highlighted = (h + 1) % completion.option_count
                self._update_completion_prompts()
        elif event.key == "shift+tab":
            if completion.option_count > 0:
                h = completion.highlighted
                if h is None:
                    completion.highlighted = completion.option_count - 1
                else:
                    completion.highlighted = (h - 1) % completion.option_count
                self._update_completion_prompts()
        elif event.key == "down":
            if completion.option_count > 0:
                h = completion.highlighted
                if h is None:
                    completion.highlighted = 0
                else:
                    completion.highlighted = (h + 1) % completion.option_count
                self._update_completion_prompts()
        elif event.key == "up":
            if completion.option_count > 0:
                h = completion.highlighted
                if h is None:
                    completion.highlighted = completion.option_count - 1
                else:
                    completion.highlighted = (h - 1) % completion.option_count
                self._update_completion_prompts()
        elif event.key == "escape":
            self._hide_completion()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Keep ❯ prompt in sync with highlighted option."""
        self._update_completion_prompts()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle click / Enter on a completion item."""
        option_id = event.option.id
        if option_id:
            self._accept_completion(str(option_id))

    def _show_completion(self, matches: list[tuple[str, str]]) -> None:
        from rich.markup import escape

        self._completion_matches = matches
        completion = self.query_one("#completion-list", OptionList)
        completion.clear_options()
        for i, (cmd, desc) in enumerate(matches):
            is_active = (i == 0)
            prefix = "[bold #f0f6fc]❯[/bold #f0f6fc] " if is_active else "  "
            cmd_style = "bold #f0f6fc" if is_active else "#c9d1d9"
            prompt = f"{prefix}[{cmd_style}]{escape(cmd)}[/{cmd_style}]   [#8b949e]{escape(desc)}[/#8b949e]"
            completion.add_option(Option(prompt, id=cmd))
        completion.highlighted = 0
        completion.add_class("visible")
        self.query_one("#chat-input", ChatInput).show_completion = True

    def _update_completion_prompts(self) -> None:
        from rich.markup import escape

        try:
            completion = self.query_one("#completion-list", OptionList)
            h = completion.highlighted
            matches = getattr(self, "_completion_matches", [])
            for i, (cmd, desc) in enumerate(matches):
                if i >= completion.option_count:
                    break
                is_active = (i == h)
                prefix = "[bold #f0f6fc]❯[/bold #f0f6fc] " if is_active else "  "
                cmd_style = "bold #f0f6fc" if is_active else "#c9d1d9"
                prompt = f"{prefix}[{cmd_style}]{escape(cmd)}[/{cmd_style}]   [#8b949e]{escape(desc)}[/#8b949e]"
                completion.replace_option_prompt_at_index(i, prompt)
        except Exception:
            pass

    def _hide_completion(self) -> None:
        completion = self.query_one("#completion-list", OptionList)
        completion.remove_class("visible")
        self._completion_matches = []
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
            if getattr(self, "_completion_mode", "command") == "file":
                cursor_loc = chat_input.cursor_location
                lines = chat_input.text.splitlines()
                if not lines:
                    lines = [""]
                row = cursor_loc[0] if cursor_loc else 0
                col = cursor_loc[1] if cursor_loc else 0
                if row < len(lines):
                    line = lines[row]
                    prefix = line[:col]
                    at_match = re.search(r'(?:^|\s)@([^\s@]*)$', prefix)
                    if at_match:
                        token_start = at_match.start()
                        if prefix[token_start] in (" ", "\t"):
                            token_start += 1
                        suffix = line[col:]
                        insert_val = cmd if cmd.endswith("/") else cmd + " "
                        new_line = line[:token_start] + insert_val + suffix
                        lines[row] = new_line
                        chat_input.text = "\n".join(lines)
                        chat_input.cursor_location = (row, token_start + len(insert_val))
            else:
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
        run_started_monotonic = time.monotonic()
        total_usage = getattr(agent.llm, "total_usage", None)
        base_completion_tokens = (
            getattr(total_usage, "completion_tokens", 0) if total_usage else 0
        )

        # Log user message
        app.session_manager.log_event(app.session_id, "USER", text)

        original_log = agent.log
        agent.log = TUILogger(
            agent.name,
            screen=self,
            session_manager=app.session_manager,
            session_id=app.session_id,
        )
        agent.approval_callback = self._request_approval  # type: ignore[attr-defined]
        self._thought_start = time.monotonic()

        # Generation counter: if this worker is cancelled by a newer run
        # (exclusive worker), the stale finally-block must not clear the
        # busy state that the newer run just set.
        self._run_generation += 1
        generation = self._run_generation

        # Show "Processing…" in the status bar right away, until the
        # response returns (or the request fails / is interrupted).
        self._set_busy(True, "Processing…")

        result: str | None = None
        try:
            # Expand #file / #dir context inside the worker so slow disk
            # reads don't delay the user message from appearing.
            processed = await asyncio.to_thread(_process_context, text)
            result = await agent.chat(processed)
            self._update_tps_from_run(run_started_monotonic, base_completion_tokens)
            messages.add_assistant_message(result, message_index=len(agent._messages) - 1, fold=False)
            app.session_manager.log_event(app.session_id, "ASSISTANT", result)
        except asyncio.CancelledError:
            messages.add_system_message("⛔ Interrupted by user.")
            app.session_manager.log_event(app.session_id, "CANCELLED", "Interrupted by user.")
        except Exception as exc:
            messages.add_system_message(f"❌ Error: {exc}")
            app.session_manager.log_event(app.session_id, "ERROR", str(exc))
        finally:
            agent.log = original_log
            if generation == self._run_generation:
                next_state = "wait for input" if _is_waiting_for_input(result) else "idle"
                self._set_busy(False, state=next_state)
            self._sync_status_bar()

        # Auto-save (skipped when the conversation has no input at all)
        self._save_session()

    @work(exclusive=True, group="agent")
    async def _run_plan_generation(self, user_text: str) -> None:
        """Analyze intent and generate/refine a structured plan."""
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        status = self.query_one(StatusBar)

        app.session_manager.log_event(app.session_id, "PLAN_INPUT", user_text)

        self._run_generation += 1
        generation = self._run_generation
        self._set_busy(True, "Analyzing intent & planning…")
        run_started_monotonic = time.monotonic()
        total_usage = getattr(app.agent.llm, "total_usage", None)
        base_completion_tokens = (
            getattr(total_usage, "completion_tokens", 0) if total_usage else 0
        )

        try:
            processed = await asyncio.to_thread(_process_context, user_text)
            existing = self._pending_plan
            plan = await generate_plan(
                app.agent.llm,
                user_intent=self._plan_goal or processed,
                existing_plan=existing,
                feedback=processed if existing else None,
            )
            self._update_tps_from_run(run_started_monotonic, base_completion_tokens)
            self._pending_plan = plan
            if not self._plan_goal:
                self._plan_goal = processed

            md_table = format_plan_markdown(plan)
            app.agent._messages.append(LLMMessage.user(processed))
            app.agent._messages.append(LLMMessage.assistant(md_table))
            messages.add_assistant_message(md_table, message_index=len(app.agent._messages) - 1)
            app.session_manager.log_event(app.session_id, "PLAN_PROPOSAL", md_table)
        except asyncio.CancelledError:
            messages.add_system_message("⛔ Interrupted by user.")
            app.session_manager.log_event(app.session_id, "CANCELLED", "Interrupted by user.")
        except Exception as exc:
            messages.add_system_message(f"❌ Planning error: {exc}")
            app.session_manager.log_event(app.session_id, "ERROR", str(exc))
        finally:
            if generation == self._run_generation:
                next_state = "wait for input" if self._pending_plan else "idle"
                self._set_busy(False, state=next_state)
            self._sync_status_bar()

        self._save_session()

    @work(exclusive=True, group="agent")
    async def _run_plan_execution(self, plan: Plan, original_goal: str) -> None:
        """Execute subtasks in topological dependency order and synthesize final answer."""
        from agent2.app.tui.app import TUILogger, build_tui_agent

        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        status = self.query_one(StatusBar)

        app.session_manager.log_event(
            app.session_id, "PLAN_EXECUTE_START", f"Goal: {original_goal}"
        )

        self._run_generation += 1
        generation = self._run_generation
        self._set_busy(True, "Starting plan execution…")

        ordered_tasks = topological_sort_tasks(plan.tasks)
        task_results: dict[str, str] = {}
        recorded_results: list[dict[str, Any]] = []
        final_answer: str | None = None

        try:
            total = len(ordered_tasks)
            for idx, task in enumerate(ordered_tasks, 1):
                self._set_busy(True, f"Subtask [{idx}/{total}] (#{task.id})…")
                messages.add_system_message(
                    f"▶ 正在执行子任务 [{idx}/{total}] (ID: {task.id}): {task.description}"
                )

                # Assemble isolated context: only task dependencies and context needed
                dep_contexts = []
                for dep_id in task.dependencies:
                    if dep_id in task_results:
                        dep_contexts.append(
                            f"• 前序任务 #{dep_id} 结果:\n{task_results[dep_id]}"
                        )
                dep_text = "\n\n".join(dep_contexts) if dep_contexts else "无（无前序依赖）"

                subtask_prompt = (
                    f"【子任务目标】\n{task.description}\n\n"
                    f"【所需特定上下文】\n{task.context_needed or '无'}\n\n"
                    f"【依赖任务输出】\n{dep_text}\n\n"
                    "请根据上述特定上下文和依赖任务输出，使用可用工具完成该子任务，并提供清晰准确的执行结果总结。"
                )

                # Create dedicated subagent with isolated context
                subagent = build_tui_agent(
                    model=app.agent.llm.model,
                    mode="agent",
                )
                subagent.log = TUILogger(
                    f"SubAgent-{task.id}",
                    screen=self,
                    session_manager=app.session_manager,
                    session_id=app.session_id,
                )
                subagent.approval_callback = self._request_approval
                self._thought_start = time.monotonic()

                # Execute subtask. Aggregate usage in ``finally`` so tokens
                # consumed by a failed or cancelled subtask are still counted.
                try:
                    res = await subagent.run(subtask_prompt)
                finally:
                    if hasattr(subagent.llm, "total_usage") and subagent.llm.total_usage:
                        app.agent.llm.total_usage = app.agent.llm.total_usage + subagent.llm.total_usage
                    self._sync_status_bar()
                task_results[task.id] = res
                recorded_results.append({
                    "id": task.id,
                    "description": task.description,
                    "result": res,
                })
                messages.add_system_message(
                    f"✓ 子任务 [{idx}/{total}] (ID: {task.id}) 执行完成。"
                )

            # Synthesize final answer from all subtask results
            self._set_busy(True, "Synthesizing final answer…")
            synth_started_monotonic = time.monotonic()
            total_usage = getattr(app.agent.llm, "total_usage", None)
            base_completion_tokens = (
                getattr(total_usage, "completion_tokens", 0) if total_usage else 0
            )
            final_answer = await synthesize_plan_results(
                app.agent.llm,
                goal=original_goal,
                task_results=recorded_results,
            )
            self._update_tps_from_run(synth_started_monotonic, base_completion_tokens)
            app.session_manager.log_event(app.session_id, "FINAL_ANSWER", final_answer)
            if not any(m.role == Role.USER and m.content == original_goal for m in app.agent._messages):
                app.agent._messages.append(LLMMessage.user(original_goal))
            app.agent._messages.append(LLMMessage.assistant(final_answer))
            messages.add_assistant_message(final_answer, message_index=len(app.agent._messages) - 1)

        except asyncio.CancelledError:
            messages.add_system_message("⛔ Interrupted by user.")
            app.session_manager.log_event(app.session_id, "CANCELLED", "Interrupted by user.")
        except Exception as exc:
            messages.add_system_message(f"❌ Execution error: {exc}")
            app.session_manager.log_event(app.session_id, "ERROR", str(exc))
        finally:
            if generation == self._run_generation:
                next_state = "wait for input" if _is_waiting_for_input(final_answer) else "idle"
                self._set_busy(False, state=next_state)
            self._sync_status_bar()

        self._save_session()

    @work(exclusive=True, group="agent")
    async def _compact_conversation(self, keep_turns: int = 1) -> None:
        """Compact conversation history by semantically summarizing past rounds."""
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)

        self._run_generation += 1
        generation = self._run_generation
        self._set_busy(True, "Compacting conversation…")
        messages.add_system_message("🧹 正在压缩对话历史上下文...")

        try:
            stats = await app.agent.compact(keep_recent_turns=keep_turns)
            if stats.get("status") == "skipped":
                reason = stats.get("reason", "Not enough turns to compact")
                messages.add_system_message(f"⚠️ 对话未压缩：{reason}。")
            else:
                messages.clear_messages()
                self._rebuild_messages()
                self._save_session()
                self._sync_status_bar()
                messages.add_system_message(
                    f"🧹 对话上下文已压缩：原 {stats['messages_before']} 条消息已精简为 {stats['messages_after']} 条消息。"
                )
                app.session_manager.log_event(
                    app.session_id,
                    "COMPACT",
                    f"Compacted from {stats['messages_before']} to {stats['messages_after']} messages",
                )
        except Exception as exc:
            messages.add_system_message(f"❌ 压缩对话上下文失败：{exc}")
            app.session_manager.log_event(app.session_id, "ERROR", f"Compact error: {exc}")
        finally:
            if generation == self._run_generation:
                self._set_busy(False)
            self._sync_status_bar()

    # ── HITL approval via Future ────────────────────────────────

    async def _request_approval(self, tool_call) -> str:  # type: ignore[type-arg]
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        messages = self.query_one("#messages", MessageList)

        self._set_busy(False, state="wait for input")
        self._sync_status_bar()

        def on_decision(result: str) -> None:
            if not future.done():
                future.set_result(result or "reject")

        messages.add_confirm_card(
            tool_call.name,
            tool_call.arguments,
            on_decision=on_decision,
        )
        decision = await future
        self._set_busy(True, "Processing…")
        self._sync_status_bar()
        return decision

    # ── TUI-logger event handlers ───────────────────────────────

    def on_thought_received(self, event: ThoughtReceived) -> None:
        elapsed = time.monotonic() - (self._thought_start or time.monotonic())
        messages = self.query_one("#messages", MessageList)
        messages.add_thinking_block(event.content, event.step, elapsed)
        self._sync_status_bar()

    def on_tool_call_started(self, event: ToolCallStarted) -> None:
        messages = self.query_one("#messages", MessageList)
        self._current_tool_name = event.tool_name
        self._current_tool_started_at = time.time()
        self._current_tool_start_monotonic = time.monotonic()
        self._current_tool_card = messages.add_tool_card(
            event.tool_name,
            event.arguments,
        )

    def on_tool_call_completed(self, event: ToolCallCompleted) -> None:
        card = self._current_tool_card
        duration: float | None = None
        started_at: float | None = self._current_tool_started_at
        if card is not None:
            card.set_result(
                event.content, is_error=event.is_error,
            )
            self._current_tool_card = None
            self.query_one("#messages", MessageList)._maybe_scroll_to_bottom()
            duration = card.duration
            started_at = card.started_at
        elif self._current_tool_start_monotonic is not None:
            duration = time.monotonic() - self._current_tool_start_monotonic
        if duration is not None:
            self._record_long_operation(
                self._current_tool_name or "tool",
                duration,
                started_at,
            )
        self._current_tool_name = None
        self._current_tool_started_at = None
        self._current_tool_start_monotonic = None
        self._set_busy(True, "Processing…")
        self._sync_status_bar()

    def on_status_text(self, event: StatusText) -> None:
        self._set_busy(True, event.text)

    # ── Slash commands ──────────────────────────────────────────

    async def _handle_command(self, text: str) -> None:
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

        elif cmd == "/plan":
            self._switch_mode("plan")
            if arg:
                await self._mount_and_render_user_message(arg)
                self._run_plan_generation(arg)
            else:
                messages.add_system_message(
                    "📋 已激活 Plan 模式。请输入您的任务目标以分析意图并生成任务列表。"
                )

        elif cmd == "/ask":
            self._switch_mode("ask")
            if arg:
                await self._mount_and_render_user_message(arg)
                self._run_agent(arg)
            else:
                messages.add_system_message(
                    "💬 已激活 Ask 模式（只读）。所有文件写入与命令执行操作已被禁止。"
                )

        elif cmd == "/agent":
            self._switch_mode("agent")
            if arg:
                await self._mount_and_render_user_message(arg)
                self._run_agent(arg)
            else:
                messages.add_system_message(
                    "🤖 已切换至 Agent 模式（缺省模式）。完整工具调用已就绪。"
                )

        elif cmd in ("/yolo", "/autopilot"):
            sub = arg.lower() if arg else "show"
            if sub == "on":
                if hasattr(app.agent, "set_yolo"):
                    app.agent.set_yolo(True)
                else:
                    app.agent.yolo = True  # type: ignore[attr-defined]
                self._sync_status_bar()
                messages.add_system_message(
                    "🚀 YOLO (Autopilot) 模式已开启：自动允许所有操作，由 LLM 自行判断并做出选择。"
                )
            elif sub == "off":
                if hasattr(app.agent, "set_yolo"):
                    app.agent.set_yolo(False)
                else:
                    app.agent.yolo = False  # type: ignore[attr-defined]
                self._sync_status_bar()
                messages.add_system_message("🛑 YOLO (Autopilot) 模式已关闭。")
            elif sub == "show":
                status_text = "ON" if getattr(app.agent, "yolo", False) else "OFF"
                messages.add_system_message(f"YOLO (Autopilot) 模式当前状态: [bold]{status_text}[/bold]")
            else:
                messages.add_system_message("Usage: /yolo [on|off|show]")

        elif cmd in ("/allow-all", "/allowall"):
            sub = arg.lower() if arg else "show"
            if sub == "on":
                if hasattr(app.agent, "set_allow_all"):
                    app.agent.set_allow_all(True)
                else:
                    app.agent.allow_all = True  # type: ignore[attr-defined]
                self._sync_status_bar()
                messages.add_system_message("🔓 Allow-all 模式已开启：自动允许所有操作。")
            elif sub == "off":
                if hasattr(app.agent, "set_allow_all"):
                    app.agent.set_allow_all(False)
                else:
                    app.agent.allow_all = False  # type: ignore[attr-defined]
                self._sync_status_bar()
                messages.add_system_message("🔒 Allow-all 模式已关闭。")
            elif sub == "show":
                status_text = "ON" if getattr(app.agent, "allow_all", False) else "OFF"
                messages.add_system_message(f"Allow-all 模式当前状态: [bold]{status_text}[/bold]")
            else:
                messages.add_system_message("Usage: /allow-all [on|off|show]")

        elif cmd == "/clear":
            messages.clear_messages()
            messages.mount(WelcomeBanner(id="welcome-banner"))
            messages.add_system_message("🧹 Display cleared.")

        elif cmd == "/compact":
            if self.query_one(StatusBar).busy:
                messages.add_system_message("⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。")
                return

            keep_turns = 1
            if arg and arg.strip().isdigit():
                keep_turns = max(0, int(arg.strip()))

            self._compact_conversation(keep_turns)

        elif cmd == "/retry":
            if self.query_one(StatusBar).busy:
                messages.add_system_message("⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。")
                return

            user_indices = [
                i for i, m in enumerate(app.agent._messages)
                if m.role == Role.USER
            ]
            if not user_indices:
                messages.add_system_message("⚠️ 当前会话没有可重试的对话轮次。")
                return

            last_user_idx = user_indices[-1]
            last_user_msg = app.agent._messages[last_user_idx]
            last_user_text = last_user_msg.content or ""

            app.agent.rewind_to(last_user_idx, inclusive=False)
            messages.clear_messages()
            self._rebuild_messages()
            self._save_session()
            self._sync_status_bar()

            await self._mount_and_render_user_message(
                last_user_text, message_index=len(app.agent._messages)
            )
            messages.add_system_message("🔄 正在重新生成回复...")
            app.session_manager.log_event(
                app.session_id, "RETRY", f"Retrying user message at index {last_user_idx}"
            )
            self._run_agent(last_user_text)

        elif cmd in ("/continue", "/c"):
            if self.query_one(StatusBar).busy:
                messages.add_system_message("⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。")
                return

            if not self._session_has_input():
                messages.add_system_message("⚠️ 当前会话还没有任务，无法继续。")
                return

            continue_prompt = arg or "请继续完成上述任务。"
            await self._mount_and_render_user_message(
                continue_prompt, message_index=len(app.agent._messages)
            )
            messages.add_system_message("▶ 继续执行任务...")
            app.session_manager.log_event(app.session_id, "CONTINUE", continue_prompt)
            self._run_agent(continue_prompt)


        elif cmd == "/rewind":
            if self.query_one(StatusBar).busy:
                messages.add_system_message("⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。")
                return

            user_indices = [
                i for i, m in enumerate(app.agent._messages)
                if m.role == Role.USER
            ]
            if not user_indices:
                messages.add_system_message("⚠️ 当前会话没有可回退的对话轮次。")
                return

            last_user_idx = user_indices[-1]
            last_user_msg = app.agent._messages[last_user_idx]
            last_user_text = last_user_msg.content or ""

            app.agent.rewind(1)
            messages.clear_messages()
            self._rebuild_messages()

            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.clear()
            if last_user_text:
                chat_input.insert(last_user_text)
            chat_input.focus()

            self._save_session()
            self._sync_status_bar()
            messages.add_system_message("⏪ 已回退到上一轮对话。")
            app.session_manager.log_event(
                app.session_id, "REWIND", f"Rewound to previous round (index {last_user_idx})"
            )

        elif cmd == "/fork":
            if self.query_one(StatusBar).busy:
                messages.add_system_message("⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。")
                return

            if not self._session_has_input():
                messages.add_system_message("当前会话还没有内容，无法 fork。")
                return

            self._save_session()
            new_id = uuid.uuid4().hex[:8]
            new_title = arg.strip() if arg else f"{app.session_title or 'Session'} (fork)"
            new_agent = app.agent.fork()

            app.session_id = new_id
            app.session_title = new_title
            app.agent = new_agent
            app.session_manager.save(new_id, app.agent.to_dict(), title=new_title)

            messages.add_system_message(
                f"🍴 已克隆当前对话为新会话 [bold cyan]{new_id}[/bold cyan] ({new_title})，后续对话将在此继续。"
            )
            self._sync_status_bar()
            app.session_manager.log_event(
                new_id, "FORK", f"Forked full conversation from previous session"
            )

        elif cmd == "/new":
            self._save_session()
            app.agent.reset()
            app.new_session_id()
            self._pending_plan = None
            self._plan_goal = ""
            messages.clear_messages()
            self._reset_usage()
            self._reset_session_metrics()
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

        elif cmd == "/export":
            if not self._session_has_input():
                messages.add_system_message("当前会话还没有内容，无法导出。")
                return
            app.session_manager.save(
                app.session_id,
                app.agent.to_dict(),
                title=app.session_title or "",
            )
            try:
                out_path = app.session_manager.export(
                    app.session_id,
                    dest_path=arg,
                )
                messages.add_system_message(
                    f"📁 Conversation exported to: [bold cyan]{out_path}[/bold cyan]"
                )
            except Exception as exc:
                messages.add_system_message(f"❌ Export failed: {exc}")

        elif cmd in ("/help", "/h"):
            messages.add_system_message(
                "[bold cyan]Modes[/bold cyan]\n"
                "  /plan [goal]    Plan mode: break down tasks, confirm, and execute with subagents\n"
                "  /ask [query]    Ask mode: read-only Q&A (write & execute operations disabled)\n"
                "  /agent [prompt] Agent mode (default): full autonomous agent with tools\n"
                "\n[bold cyan]Commands[/bold cyan]\n"
                "  /model [name]   Switch model\n"
                "  /skills         List available skills\n"
                "  /tools          List currently active tools\n"
                "  /mcp            Manage MCP servers (list, enable, disable)\n"
                "  /<skill> [msg]  Invoke a skill by name\n"
                "  /clear          Clear display\n"
                "  /retry          Retry last query / regenerate response\n"
                "  /continue       Continue execution if paused or reached max iterations\n"
                "  /rewind         Rewind to previous round\n"
                "  /fork [title]   Fork current session and continue\n"
                "  /new            New session\n"
                "  /sessions       List & manage sessions (resume/rename/delete)\n"
                "  /resume [id]    Resume session\n"
                "  /rename <title> Rename current session\n"
                "  /export [path]  Export conversation history\n"
                "  /cfg            Open configuration in system editor\n"
                "  /yolo [on|off|show]      YOLO / Autopilot mode: auto-approve operations & autonomous decisions\n"
                "  /allow-all [on|off|show] Allow-all mode: auto-approve all operations\n"
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

        elif cmd == "/skills":
            from agent2.context import discover_skills

            if not arg:
                self._open_skills_dialog()
            elif arg.strip() == "reload":
                skills = discover_skills()
                if getattr(app, "context", None):
                    app.context.skills = skills
                messages.add_system_message(
                    f"🔄 Reloaded {len(skills)} skills from disk.\n"
                    + "\n".join(f"  • [bold green]/{s.name}[/bold green] ({s.source})" for s in skills)
                )
            else:
                target = arg.strip().split()[-1].lstrip("/")
                ctx = getattr(app, "context", None)
                skill = ctx.get_skill(target) if ctx else None
                if not skill:
                    for s in discover_skills():
                        if s.name.lower() == target.lower():
                            skill = s
                            break
                if skill:
                    messages.add_system_message(
                        f"[bold cyan]Skill: {skill.name}[/bold cyan]  [dim dodger_blue1]({skill.source})[/dim dodger_blue1]\n"
                        f"[dim]Path: {skill.path}[/dim]\n\n"
                        f"{skill.description}\n\n"
                        f"---\n\n"
                        f"{skill.body or skill.content}"
                    )
                else:
                    messages.add_system_message(f"Skill '{target}' not found. Type /skills to browse.")

        elif cmd in ("/tools", "/tool"):
            tools = app.agent.tool_registry.list_tools()
            if not tools:
                messages.add_system_message("ℹ️ No tools currently registered.")
            else:
                lines = [f"[bold cyan]Active Tools ({len(tools)} registered):[/bold cyan]"]
                for t in tools:
                    lines.append(f"\n  • [bold green]{t.name}[/bold green]")
                    if t.description:
                        lines.append(f"    [dim]{t.description.strip()}[/dim]")
                messages.add_system_message("\n".join(lines))

        elif cmd == "/mcp":
            await self._handle_mcp(arg)

        elif cmd in ("/cfg", "/config"):
            self._handle_cfg()

        else:
            # ── Dynamic skill invocation: /<skill_name> [prompt] ──
            from agent2.context import discover_skills

            ctx = getattr(app, "context", None)
            skill_name = cmd.lstrip("/")
            skill = ctx.get_skill(skill_name) if ctx else None
            if not skill:
                for s in discover_skills():
                    if s.name.lower() == skill_name.lower():
                        skill = s
                        if ctx:
                            ctx.skills = discover_skills()
                        break

            if skill:
                skill_prompt = (
                    f"[Skill: {skill.name}]\n"
                    f"Description: {skill.description}\n\n"
                    f"{skill.content}\n\n"
                    f"---\n\n"
                    f"{arg or 'Please proceed with your expertise.'}"
                )
                display_msg = f"/{skill.name} {arg}" if arg else f"/{skill.name}"
                await self._mount_and_render_user_message(display_msg)
                self._run_agent(skill_prompt)
            else:
                messages.add_system_message(
                    f"Unknown command: {cmd}.  Type /help for help."
                )

    def _handle_resume(self, arg: str | None) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        sessions = app.session_manager.list_sessions()

        if arg:
            match = app.session_manager.find_session(arg)
            if match:
                app.load_session(match["id"])
                messages.clear_messages()
                self._rebuild_messages()
                self._reset_session_metrics()
                self._sync_status_bar()
                messages.add_system_message(
                    f"🔄 Session {match['id'][:8]} restored."
                )
            else:
                messages.add_system_message(f"Session matching '{arg}' not found.")
            return

        self._open_sessions_dialog()

    async def _handle_mcp(self, arg: str | None) -> None:
        from agent2.app.config import load_config, update_mcp_server_disabled
        from agent2.mcp import MCPManager, MCPServerConfig

        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)

        raw_arg = (arg or "").strip()
        parts = raw_arg.split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        # Load configuration
        cfg = load_config()
        configured_servers: dict[str, Any] = dict(cfg.mcp_servers)

        # Ensure manager instance
        manager: MCPManager | None = getattr(app, "mcp_manager", None)
        if manager is None:
            servers = {
                k: MCPServerConfig.model_validate(v)
                for k, v in configured_servers.items()
            }
            manager = MCPManager(servers)
            app.mcp_manager = manager
            app.agent.mcp_manager = manager  # type: ignore[attr-defined]

        if not sub or sub == "list":
            if not configured_servers:
                messages.add_system_message(
                    "ℹ️ No MCP servers configured.\n\n"
                    "Configure servers in [bold]~/.config/agent2/config.json[/bold] under [cyan]\"mcp_servers\"[/cyan]."
                )
                return

            lines = [f"[bold cyan]MCP Servers ({len(configured_servers)} configured):[/bold cyan]"]
            for name, raw_srv in configured_servers.items():
                srv_cfg = MCPServerConfig.model_validate(raw_srv)
                is_disabled = srv_cfg.disabled
                status_badge = "[dim red]○ disabled[/dim red]" if is_disabled else "[bold green]● enabled[/bold green]"
                proto = srv_cfg.type.upper()
                lines.append(f"\n  • [bold]{name}[/bold] {status_badge} ({proto})")

                if srv_cfg.type == "stdio":
                    cmd_str = srv_cfg.command or ""
                    if srv_cfg.args:
                        cmd_str += " " + " ".join(srv_cfg.args)
                    lines.append(f"    [dim]Command:[/dim] {cmd_str}")
                else:
                    lines.append(f"    [dim]URL:[/dim] {srv_cfg.url or 'N/A'}")
                    if srv_cfg.headers:
                        headers_str = ", ".join(srv_cfg.headers.keys())
                        lines.append(f"    [dim]Headers:[/dim] {headers_str}")

                tools = manager.get_server_tools(name)
                if tools:
                    tool_names = ", ".join(f"[green]{t.name}[/green]" for t in tools)
                    lines.append(f"    [dim]Active Tools ({len(tools)}):[/dim] {tool_names}")
                elif not is_disabled:
                    lines.append("    [dim]Active Tools:[/dim] [dim italic]not connected or no tools discovered[/dim italic]")

                if srv_cfg.always_allow:
                    allow_str = ", ".join(srv_cfg.always_allow)
                    lines.append(f"    [dim]Always Allow:[/dim] [yellow]{allow_str}[/yellow]")

            lines.append("\n[bold cyan]Commands:[/bold cyan]")
            lines.append("  /mcp list               List all MCP servers")
            lines.append("  /mcp enable <name>      Enable an MCP server and connect")
            lines.append("  /mcp disable <name>     Disable an MCP server and disconnect")
            messages.add_system_message("\n".join(lines))

        elif sub == "enable":
            if not sub_arg:
                messages.add_system_message("Usage: /mcp enable <server-name>")
                return

            srv_name = sub_arg
            matched_key = None
            for k in configured_servers:
                if k.lower() == srv_name.lower():
                    matched_key = k
                    break

            if not matched_key:
                messages.add_system_message(
                    f"❌ MCP server '[bold]{srv_name}[/bold]' not found in ~/.config/agent2/config.json."
                )
                return

            srv_cfg = MCPServerConfig.model_validate(configured_servers[matched_key])
            update_mcp_server_disabled(matched_key, False)
            srv_cfg.disabled = False
            manager.servers[matched_key] = srv_cfg

            try:
                tools = await manager.connect_server(matched_key)
                for t in tools:
                    if t.name in app.agent.tool_registry:
                        app.agent.tool_registry.unregister(t.name)
                    app.agent.tool_registry.register(t)
                app.agent._auto_approved.update(manager.always_allow_tools)
                tool_names = ", ".join(f"[green]{t.name}[/green]" for t in tools) if tools else "none"
                messages.add_system_message(
                    f"✅ MCP server '[bold green]{matched_key}[/bold green]' enabled.\n"
                    f"Discovered {len(tools)} tools: {tool_names}"
                )
            except Exception as exc:
                messages.add_system_message(
                    f"⚠️ MCP server '[bold]{matched_key}[/bold]' enabled in config, but failed to connect: {exc}"
                )

        elif sub == "disable":
            if not sub_arg:
                messages.add_system_message("Usage: /mcp disable <server-name>")
                return

            srv_name = sub_arg
            matched_key = None
            for k in configured_servers:
                if k.lower() == srv_name.lower():
                    matched_key = k
                    break

            if not matched_key:
                messages.add_system_message(
                    f"❌ MCP server '[bold]{srv_name}[/bold]' not found in ~/.config/agent2/config.json."
                )
                return

            srv_cfg = MCPServerConfig.model_validate(configured_servers[matched_key])
            if srv_cfg.disabled and not manager.is_server_connected(matched_key):
                messages.add_system_message(f"ℹ️ MCP server '[bold]{matched_key}[/bold]' is already disabled.")
                return

            update_mcp_server_disabled(matched_key, True)
            srv_cfg.disabled = True
            manager.servers[matched_key] = srv_cfg

            removed_tools = await manager.disconnect_server(matched_key)
            for t_name in removed_tools:
                app.agent.tool_registry.unregister(t_name)
                app.agent._auto_approved.discard(t_name)

            messages.add_system_message(
                f"🛑 MCP server '[bold red]{matched_key}[/bold red]' disabled and disconnected. "
                f"Removed {len(removed_tools)} tools."
            )

        else:
            messages.add_system_message(
                "Usage:\n"
                "  /mcp list\n"
                "  /mcp enable <server-name>\n"
                "  /mcp disable <server-name>"
            )

    def _handle_cfg(self) -> None:
        """Open ~/.config/agent2/config.json in system editor with backup protection."""
        from agent2.app.config import (
            get_system_editor,
            prepare_and_backup_config,
            validate_after_edit,
        )

        messages = self.query_one("#messages", MessageList)
        backed_up, file_path = prepare_and_backup_config()
        editor_cmd = get_system_editor()
        editor_name = " ".join(editor_cmd)

        messages.add_system_message(
            f"📝 Opening [bold]{file_path}[/bold] with [cyan]{editor_name}[/cyan]..."
        )

        import subprocess

        try:
            can_suspend = getattr(getattr(self.app, "_driver", None), "can_suspend", False)
            if can_suspend:
                with self.app.suspend():
                    subprocess.run([*editor_cmd, file_path], check=True)
            else:
                subprocess.run([*editor_cmd, file_path], check=True)
        except Exception as exc:
            messages.add_system_message(f"❌ Failed to launch editor '{editor_name}': {exc}")
            return

        valid, status_msg = validate_after_edit()
        if valid:
            messages.add_system_message(f"✅ {status_msg}")
        else:
            messages.add_system_message(f"⚠️ {status_msg}")

    def _rebuild_messages(self) -> None:
        """Re-populate the message list from the agent's history."""
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        tool_results: dict[str, Any] = {}
        for m in app.agent.messages:
            if m.role == Role.TOOL and m.tool_result is not None:
                tool_results[m.tool_result.tool_call_id] = m.tool_result

        # Find the last assistant message with content (to render unfolded)
        last_assistant_idx: int | None = None
        for idx, msg in enumerate(app.agent.messages):
            if msg.role == Role.ASSISTANT and msg.content:
                last_assistant_idx = idx

        for idx, msg in enumerate(app.agent.messages):
            if msg.role == Role.USER:
                messages.add_user_message(msg.content or "", message_index=idx)
            elif msg.role == Role.ASSISTANT:
                is_last = (idx == last_assistant_idx)
                if msg.content:
                    messages.add_assistant_message(msg.content, message_index=idx, fold=not is_last)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tr = tool_results.get(tc.id)
                        if tr is not None:
                            messages.add_tool_card(
                                tc.name,
                                tc.arguments or {},
                                result=tr.content,
                                is_error=tr.is_error,
                            )
                        else:
                            messages.add_tool_card(
                                tc.name,
                                tc.arguments or {},
                            )
                elif not msg.content:
                    messages.add_assistant_message("", message_index=idx)

    # ── Interrupt / Quit / Selection ────────────────────────────

    def action_cancel_selection(self) -> None:
        """Escape: close the shortcut panel, clear selection, and focus the input."""
        try:
            shortcut_help = self.query_one(ShortcutHelp)
            if shortcut_help.visible:
                shortcut_help.hide_help()
                self.query_one("#chat-input", ChatInput).focus()
                return
        except Exception:
            pass
        messages = self.query_one("#messages", MessageList)
        messages.deselect_all()
        self.query_one("#chat-input", ChatInput).focus()

    def action_interrupt(self) -> None:
        """Ctrl+C: cancel the running agent worker (does not exit)."""
        for w in self.app.workers:
            if w.group == "agent" and w.is_running:
                w.cancel()
                self._set_busy(False)
                return
        self._set_busy(False)

    def action_toggle_tool_results(self) -> None:
        """Ctrl+O: toggle expand/collapse state on all tool results & folded content."""
        from textual.widgets import Collapsible

        results = list(self.query_one("#messages", MessageList).query(Collapsible))
        if not results:
            return
        any_collapsed = any(r.collapsed for r in results)
        for r in results:
            r.collapsed = not any_collapsed

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

    # ── Point Rewind & Fork & Retry event handlers ───────────────

    def on_rewind_requested(self, event: RewindRequested) -> None:
        if self.query_one(StatusBar).busy:
            self.query_one("#messages", MessageList).add_system_message(
                "⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。"
            )
            return
        self._handle_point_rewind(event.message_widget, event.message_index)

    async def on_retry_requested(self, event: RetryRequested) -> None:
        if self.query_one(StatusBar).busy:
            self.query_one("#messages", MessageList).add_system_message(
                "⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。"
            )
            return
        await self._handle_point_retry(event.message_widget, event.message_index)

    async def on_continue_requested(self, event: ContinueRequested) -> None:
        if self.query_one(StatusBar).busy:
            self.query_one("#messages", MessageList).add_system_message(
                "⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。"
            )
            return
        app: Agent2App = self.app  # type: ignore[assignment]
        messages = self.query_one("#messages", MessageList)
        continue_prompt = "请继续完成上述任务。"
        await self._mount_and_render_user_message(
            continue_prompt, message_index=len(app.agent._messages)
        )
        messages.add_system_message("▶ 继续执行任务...")
        app.session_manager.log_event(app.session_id, "CONTINUE", continue_prompt)
        self._run_agent(continue_prompt)


    def on_fork_requested(self, event: ForkRequested) -> None:
        if self.query_one(StatusBar).busy:
            self.query_one("#messages", MessageList).add_system_message(
                "⚠️ Agent 正在执行中，请先等待或按 Ctrl+C 中断。"
            )
            return
        self._handle_point_fork(event.message_widget, event.message_index)

    def _resolve_message_index(self, widget: Any, message_index: int | None) -> int | None:
        app: Agent2App = self.app  # type: ignore[assignment]
        msgs = app.agent._messages
        if message_index is not None and 0 <= message_index < len(msgs):
            return message_index

        if isinstance(widget, UserMessage):
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].role == Role.USER and msgs[i].content == widget._text:
                    return i
        elif isinstance(widget, AssistantMessage):
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].role == Role.ASSISTANT and msgs[i].content == widget._content:
                    return i
        return None

    def _handle_point_rewind(self, widget: Any, message_index: int | None) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        idx = self._resolve_message_index(widget, message_index)
        if idx is None:
            return

        messages = self.query_one("#messages", MessageList)
        chat_input = self.query_one("#chat-input", ChatInput)

        if isinstance(widget, UserMessage):
            app.agent.rewind_to(idx, inclusive=False)
            chat_input.clear()
            if widget._text:
                chat_input.insert(widget._text)
            chat_input.focus()
            messages.clear_messages()
            self._rebuild_messages()
            self._save_session()
            self._sync_status_bar()
            messages.add_system_message("⏪ 已回退至该消息之前，已将内容填入输入框。")
            app.session_manager.log_event(
                app.session_id, "REWIND", f"Rewound to before user message at index {idx}"
            )
        elif isinstance(widget, AssistantMessage):
            app.agent.rewind_to(idx, inclusive=True)
            messages.clear_messages()
            self._rebuild_messages()
            self._save_session()
            self._sync_status_bar()
            chat_input.focus()
            messages.add_system_message("⏪ 已回退至该助手回复。")
            app.session_manager.log_event(
                app.session_id, "REWIND", f"Rewound to assistant message at index {idx}"
            )

    def _handle_point_fork(self, widget: Any, message_index: int | None) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        idx = self._resolve_message_index(widget, message_index)
        if idx is None:
            return

        self._save_session()

        messages = self.query_one("#messages", MessageList)
        chat_input = self.query_one("#chat-input", ChatInput)
        new_agent = app.agent.fork()
        new_id = uuid.uuid4().hex[:8]
        new_title = f"{app.session_title or 'Session'} (fork)"

        if isinstance(widget, UserMessage):
            new_agent._messages = [
                m.model_copy(deep=True) for m in app.agent._messages[:idx]
            ]
            app.session_id = new_id
            app.session_title = new_title
            app.agent = new_agent
            app.session_manager.save(new_id, app.agent.to_dict(), title=new_title)

            messages.clear_messages()
            self._rebuild_messages()
            chat_input.clear()
            if widget._text:
                chat_input.insert(widget._text)
            chat_input.focus()
            messages.add_system_message(
                f"🍴 已从该节点克隆为新会话 [bold cyan]{new_id}[/bold cyan] ({new_title})，已将该消息填入输入框。"
            )
            self._sync_status_bar()
            app.session_manager.log_event(
                new_id, "FORK", f"Forked from session before user message at index {idx}"
            )
        elif isinstance(widget, AssistantMessage):
            new_agent._messages = [
                m.model_copy(deep=True) for m in app.agent._messages[:idx + 1]
            ]
            app.session_id = new_id
            app.session_title = new_title
            app.agent = new_agent
            app.session_manager.save(new_id, app.agent.to_dict(), title=new_title)

            messages.clear_messages()
            self._rebuild_messages()
            chat_input.focus()
            messages.add_system_message(
                f"🍴 已从该节点克隆为新会话 [bold cyan]{new_id}[/bold cyan] ({new_title})，后续对话将在此继续。"
            )
            self._sync_status_bar()
            app.session_manager.log_event(
                new_id, "FORK", f"Forked from session at assistant message index {idx}"
            )

    async def _handle_point_retry(self, widget: Any, message_index: int | None) -> None:
        app: Agent2App = self.app  # type: ignore[assignment]
        idx = self._resolve_message_index(widget, message_index)
        if idx is None:
            return

        messages = self.query_one("#messages", MessageList)

        if isinstance(widget, UserMessage):
            prompt = widget._text
            app.agent.rewind_to(idx, inclusive=False)
            messages.clear_messages()
            self._rebuild_messages()
            self._save_session()
            self._sync_status_bar()

            await self._mount_and_render_user_message(prompt, message_index=len(app.agent._messages))
            messages.add_system_message("🔄 正在重新生成回复...")
            app.session_manager.log_event(
                app.session_id, "RETRY", f"Retrying user message at index {idx}"
            )
            self._run_agent(prompt)

        elif isinstance(widget, AssistantMessage):
            user_idx = None
            for i in range(idx - 1, -1, -1):
                if app.agent._messages[i].role == Role.USER:
                    user_idx = i
                    break
            if user_idx is None:
                messages.add_system_message("⚠️ 无法找到该回复对应的用户提问。")
                return

            user_prompt = app.agent._messages[user_idx].content or ""
            app.agent.rewind_to(user_idx, inclusive=False)
            messages.clear_messages()
            self._rebuild_messages()
            self._save_session()
            self._sync_status_bar()

            await self._mount_and_render_user_message(user_prompt, message_index=len(app.agent._messages))
            messages.add_system_message("🔄 正在重新生成回复...")
            app.session_manager.log_event(
                app.session_id, "RETRY", f"Retrying from user message at index {user_idx}"
            )
            self._run_agent(user_prompt)



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
        usage = getattr(app.agent.llm, "total_usage", None)
        usage_data = usage.model_dump() if usage else None
        app.session_manager.save(
            app.session_id, app.agent.to_dict(), usage=usage_data
        )

    def _reset_usage(self) -> None:
        """Zero the LLM usage counters and the status bar token readouts.

        Called when a new conversation starts (``/new``).
        """
        app: Agent2App = self.app  # type: ignore[assignment]
        llm = app.agent.llm
        llm.total_usage = Usage()
        llm.last_usage = None
        self._tps_estimate = 0.0
        self._last_long_operation_started_at = 0.0
        status = self.query_one(StatusBar)
        status.input_tokens = 0
        status.output_tokens = 0
        status.context_tokens = 0
        status.tps = 0.0
        status.long_operation = ""
        try:
            ctx = self.query_one(ContextBar)
            ctx.input_tokens = 0
            ctx.output_tokens = 0
            ctx.context_tokens = 0
            ctx.tps = 0.0
            ctx.long_operation = ""
        except Exception:
            pass

    def _sync_status_bar(self) -> None:
        """Push model name, token usage, and mode from the app/agent to the status & context bars."""
        from agent2.app.chat import resolve_provider_or_host

        app: Agent2App = self.app  # type: ignore[assignment]
        status = self.query_one(StatusBar)
        try:
            context_bar = self.query_one(ContextBar)
        except Exception:
            context_bar = None
        llm = app.agent.llm

        provider_val = getattr(llm, "provider", None)
        base_url_val = getattr(llm, "base_url", None) or getattr(llm, "_base_url", None)
        provider_disp = resolve_provider_or_host(provider_val, base_url_val)

        mode_str = getattr(app, "mode", "agent").upper()
        status.mode = mode_str
        status.yolo = getattr(app.agent, "yolo", False)
        status.allow_all = getattr(app.agent, "allow_all", False)
        status.model_name = llm.model
        status.provider = provider_disp
        ctx_win = getattr(llm, "context_window", 0) or 0
        status.context_window = ctx_win

        in_tok = 0
        out_tok = 0
        total = getattr(llm, "total_usage", None)
        if total is not None:
            in_tok = total.prompt_tokens
            out_tok = total.completion_tokens
            status.input_tokens = in_tok
            status.output_tokens = out_tok

        ctx_tok = 0
        last = getattr(llm, "last_usage", None)
        if last is not None and last.prompt_tokens:
            ctx_tok = last.prompt_tokens
            status.context_tokens = ctx_tok

        total_cost = getattr(llm, "total_cost", 0.0) or 0.0
        status.cost = total_cost

        tps = self._resolve_tps()
        status.tps = tps
        if context_bar is not None:
            context_bar.model_name = llm.model
            context_bar.provider = provider_disp
            context_bar.context_window = ctx_win
            context_bar.input_tokens = in_tok
            context_bar.output_tokens = out_tok
            context_bar.context_tokens = ctx_tok
            context_bar.cost = total_cost
            context_bar.tps = tps
            context_bar.busy = status.busy
            context_bar.status_text = status.status_text
            context_bar.status_state = getattr(status, "status_state", "idle")

        # Surface slow provider requests in the duration/start-time readout.
        last_duration = getattr(llm, "last_request_duration", None)
        last_started_at = getattr(llm, "last_request_started_at", None)
        if last_duration is not None and last_started_at is not None:
            self._record_long_operation(
                f"LLM {llm.model}",
                last_duration,
                last_started_at,
            )


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

    def _read_at_ref(m: re.Match[str]) -> str:
        raw_path = m.group(1).strip()
        if raw_path.startswith("<") and raw_path.endswith(">"):
            raw_path = raw_path[1:-1].strip()
        p = Path(raw_path).expanduser()
        if not p.exists():
            return m.group(0)
        if p.is_dir():
            try:
                entries = sorted(p.iterdir())
                listing = "\n".join(
                    f"{'[dir]' if e.is_dir() else '[file]'} {e.name}"
                    for e in entries
                    if not e.name.startswith(".")
                )
                return f'\n<directory path="{p}">\n{listing}\n</directory>\n'
            except Exception as exc:
                return f"\n[Error reading dir {p}: {exc}]\n"
        else:
            try:
                content = p.read_text(encoding="utf-8")
                return f'\n<file path="{p}">\n{content}\n</file>\n'
            except Exception as exc:
                return f"\n[Error reading {p}: {exc}]\n"

    text = re.sub(r"#file\s+(\S+)", _read_file, text)
    text = re.sub(r"#dir\s+(\S+)", _read_dir, text)
    text = re.sub(r"(?:^|(?<=\s))@(\S+)", _read_at_ref, text)
    return text
