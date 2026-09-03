"""Agent2 TUI application — Textual App, TUI-aware agent, and TUI logger."""

from __future__ import annotations

import time
import uuid
from typing import Any, Self

from textual.app import App

from agent2.agent.base import BaseAgent
from agent2.agent.react import ReActAgent
from agent2.app.chat import get_available_models  # noqa: F401 – re-export convenience
from agent2.app.config import get_last_model, load_config, set_last_model
from agent2.llm import create_llm
from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.tools.base import Tool
from agent2.tools.builtin import file_read, file_write, shell_exec
from agent2.utils.logging import AgentLogger

from agent2.app.tui.screens.chat import (
    ChatScreen,
    StatusText,
    ThoughtReceived,
    ToolCallCompleted,
    ToolCallStarted,
)
from agent2.app.tui.session import SessionManager
from agent2.app.tui.styles import APP_CSS


# ── TUI-specific ReAct agent with HITL ──────────────────────────


class TUIReActAgent(ReActAgent):
    """ReActAgent variant with human-in-the-loop approval and mode enforcement."""

    SAFE_TOOLS: frozenset[str] = frozenset({"file_read", "read_file", "list_directory", "web_search"})

    def __init__(self, *args: Any, mode: str = "agent", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.approval_callback: Any = None
        self._auto_approved: set[str] = set()
        self.mode = mode

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == "ask":
            if self.system_prompt == DEFAULT_SYSTEM_MSG:
                self.set_rule(ASK_SYSTEM_MSG)
        elif mode == "agent":
            if self.system_prompt == ASK_SYSTEM_MSG:
                self.set_rule(DEFAULT_SYSTEM_MSG)

    def fork(self, name: str | None = None) -> Self:
        new_agent = super().fork(name=name)
        new_agent._auto_approved = set(self._auto_approved)
        new_agent.approval_callback = self.approval_callback
        new_agent.mode = self.mode
        return new_agent

    async def _run_loop(self) -> str:
        """Execute ReAct loop with mode-filtered tool schemas."""
        from agent2.agent.base import MaxIterationsExceeded

        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")

        all_schemas = self.tool_registry.list_schemas()
        if self.mode == "ask":
            tool_schemas = [s for s in all_schemas if s.name in self.SAFE_TOOLS] or None
        else:
            tool_schemas = all_schemas or None

        for iteration in range(1, self.max_iterations + 1):
            response = await self.llm.chat(
                self._messages,
                tools=tool_schemas,
            )

            if response.has_tool_calls:
                if response.content:
                    self.log.thought(response.content)
                self._messages.append(response.message)
                tool_results = await self._execute_tool_calls(response.tool_calls)
                self._messages.extend(tool_results)
                continue

            final_answer = response.content or ""
            self.log.final_answer(final_answer)
            return final_answer

        raise MaxIterationsExceeded(
            f"Agent '{self.name}' exceeded {self.max_iterations} iterations"
        )

    async def _execute_tool_calls(self, tool_calls: list[Any]) -> list[Message]:
        results: list[Message] = []
        for tc in tool_calls:
            # Enforce read-only constraint in Ask mode
            if self.mode == "ask" and tc.name not in self.SAFE_TOOLS:
                err_msg = (
                    f"Tool '{tc.name}' is forbidden in Ask mode. "
                    "All write and execution operations are disabled."
                )
                self.log.observation(err_msg, is_error=True)
                results.append(Message.tool(tc.id, err_msg, is_error=True))
                continue

            # Gate side-effecting tools behind HITL
            needs_approval = (
                tc.name not in self.SAFE_TOOLS
                and tc.name not in self._auto_approved
                and self.approval_callback is not None
            )
            if needs_approval:
                decision: str = await self.approval_callback(tc)
                if decision == "reject":
                    self.log.observation(
                        f"User rejected execution of {tc.name}.", is_error=True,
                    )
                    results.append(
                        Message.tool(tc.id, "Execution rejected by user.", is_error=True),
                    )
                    continue
                if decision == "always":
                    self._auto_approved.add(tc.name)

            self.log.action(tc.name, tc.arguments)
            try:
                output = await self.tool_registry.execute(tc.name, **tc.arguments)
            except Exception as exc:
                output = f"Error executing {tc.name}: {exc}"
                is_error = True
            else:
                is_error = output.startswith("Error")
            self.log.observation(output, is_error=is_error)
            results.append(Message.tool(tc.id, output, is_error=is_error))
        return results


# ── TUI Logger (redirects events to the ChatScreen) ────────────


class TUILogger(AgentLogger):
    """Replaces the default rich-console logger to post Textual messages and write session logs."""

    def __init__(
        self,
        agent_name: str,
        *,
        screen: ChatScreen,
        session_manager: SessionManager | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(agent_name, verbose=False)
        self._screen = screen
        self._session_manager = session_manager
        self._session_id = session_id

    def start(self, task: str) -> None:
        self._start_time = time.monotonic()
        self._step = 0
        if self._session_manager and self._session_id:
            self._session_manager.log_event(self._session_id, "START", f"Task: {task}")

    def thought(self, content: str) -> None:
        self._step += 1
        self._screen.post_message(ThoughtReceived(content, self._step))
        if self._session_manager and self._session_id:
            self._session_manager.log_event(
                self._session_id, f"THOUGHT_STEP_{self._step}", content
            )

    def action(self, tool_name: str, arguments: dict[str, Any] | None = None) -> None:
        self._screen.post_message(ToolCallStarted(tool_name, arguments or {}))
        self._screen.post_message(StatusText(f"Running {tool_name}…"))
        if self._session_manager and self._session_id:
            self._session_manager.log_event(
                self._session_id, "ACTION", f"{tool_name}({arguments or {}})"
            )

    def observation(self, content: str, *, is_error: bool = False) -> None:
        self._screen.post_message(ToolCallCompleted(content, is_error))
        if self._session_manager and self._session_id:
            tag = "ERROR" if is_error else "OBSERVATION"
            self._session_manager.log_event(self._session_id, tag, content)

    def final_answer(self, content: str) -> None:
        if self._session_manager and self._session_id:
            self._session_manager.log_event(self._session_id, "FINAL_ANSWER", content)

    def finish(self, summary: str | None = None) -> None:
        if self._session_manager and self._session_id:
            self._session_manager.log_event(
                self._session_id, "FINISH", summary or "Task completed"
            )


# ── Textual Application ────────────────────────────────────────


DEFAULT_SYSTEM_MSG = (
    "You are a helpful assistant with access to local tools (reading/writing files, "
    "executing shell commands). Use tools proactively when needed to inspect files, "
    "run commands, or create/modify code."
)

ASK_SYSTEM_MSG = (
    "You are a helpful assistant operating in Ask mode (Read-Only). "
    "You can answer questions, explain concepts, and inspect files/directories using read-only tools. "
    "All file modifications, writing operations, and shell/command executions are strictly forbidden."
)


def restore_agent(
    agent: ReActAgent,
    session_manager: SessionManager,
    session_id: str,
) -> str | None:
    """Restore agent state from session on disk and return session title."""
    data = session_manager.load(session_id)
    agent_data = data["agent"]
    tools = list(agent.tool_registry.list_tools())
    restored = BaseAgent.from_dict(agent_data, llm=agent.llm, tools=tools)
    if not isinstance(restored, ReActAgent):
        raise ValueError(
            f"Session contains agent type '{type(restored).__name__}', expected ReActAgent."
        )
    agent.llm = restored.llm
    agent._messages = restored._messages  # noqa: SLF001
    agent.system_prompt = restored.system_prompt
    set_last_model(agent.llm.model)
    return data.get("title")


class Agent2App(App):  # type: ignore[type-arg]
    """Top-level Textual application for agent2 TUI."""

    CSS = APP_CSS
    TITLE = "Agent2 TUI"

    def __init__(
        self,
        agent: TUIReActAgent,
        session_manager: SessionManager | None = None,
        initial_message: str | None = None,
        resume_session_id: str | None = None,
        mode: str = "agent",
    ) -> None:
        super().__init__()
        self.agent = agent
        self.session_manager = session_manager or SessionManager()
        self.session_id = uuid.uuid4().hex[:8]
        self.session_title: str | None = None
        self.initial_message = initial_message
        self.mode = mode
        if hasattr(self.agent, "set_mode"):
            self.agent.set_mode(mode)
        if resume_session_id:
            self.load_session(resume_session_id)

    def on_mount(self) -> None:
        self.push_screen(ChatScreen())

    # ── public helpers used by ChatScreen ────────────────────────

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if hasattr(self.agent, "set_mode"):
            self.agent.set_mode(mode)

    def switch_model(self, model_name: str) -> None:
        self.agent.llm = create_llm(model_name)
        set_last_model(self.agent.llm.model)

    def new_session_id(self) -> None:
        self.session_id = uuid.uuid4().hex[:8]
        self.session_title = None

    def load_session(self, session_id: str) -> None:
        self.session_title = restore_agent(self.agent, self.session_manager, session_id)
        self.session_id = session_id



# ── Builder (mirrors chat.py's _build_agent) ────────────────────


def build_tui_agent(
    *,
    model: str | None = None,
    system_msg: str | None = None,
    no_tools: bool = False,
    mode: str = "agent",
) -> TUIReActAgent:
    """Create a :class:`TUIReActAgent` with sensible defaults."""
    cfg = load_config()
    name_or_model = model or get_last_model() or cfg.default or cfg.llm.model

    llm = create_llm(name_or_model)
    tools: list[Any]
    if no_tools:
        tools = []
    elif mode == "ask":
        tools = [file_read]
    else:
        tools = [file_read, file_write, shell_exec]

    if system_msg is None:
        sys_msg = ASK_SYSTEM_MSG if mode == "ask" else DEFAULT_SYSTEM_MSG
    else:
        sys_msg = system_msg

    return TUIReActAgent(
        name="assistant",
        llm=llm,
        system_prompt=sys_msg,
        tools=tools,
        verbose=True,
        mode=mode,
    )
