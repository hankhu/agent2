"""Tests for YOLO (Autopilot) mode, Allow-all mode, and Tab panel navigation."""

from __future__ import annotations

from pathlib import Path
import pytest

from agent2.app.tui.app import (
    DEFAULT_SYSTEM_MSG,
    YOLO_INSTRUCTION,
    Agent2App,
    TUIReActAgent,
)
from agent2.app.tui.screens.chat import ChatScreen
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import MessageList
from agent2.app.tui.widgets.nav_bar import TabItem, TopTabBar
from agent2.app.tui.widgets.status_bar import StatusBar
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, ToolCall
from agent2.tools.base import tool


class MockLLM(BaseLLM):
    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        super().__init__(model="test-model")
        self._responses = list(responses or [LLMResponse(message=Message.assistant("Done"))])
        self._call_count = 0

    async def chat(self, messages, tools=None):
        resp = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return resp


@tool(description="Side effect tool")
def unsafe_action(command: str) -> str:
    return f"Executed: {command}"


def test_tui_react_agent_yolo_prompt_toggle():
    llm = MockLLM()
    agent = TUIReActAgent(name="test", llm=llm)
    assert not agent.yolo
    assert not agent.allow_all
    assert YOLO_INSTRUCTION not in (agent.system_prompt or "")

    # Enable YOLO
    agent.set_yolo(True)
    assert agent.yolo
    assert YOLO_INSTRUCTION in (agent.system_prompt or "")

    # Disable YOLO
    agent.set_yolo(False)
    assert not agent.yolo
    assert YOLO_INSTRUCTION not in (agent.system_prompt or "")


def test_tui_react_agent_extra_state_and_fork():
    llm = MockLLM()
    agent = TUIReActAgent(name="test", llm=llm)
    agent.set_yolo(True)
    agent.set_allow_all(True)

    extra = agent._get_extra_state()
    assert extra["yolo"] is True
    assert extra["allow_all"] is True

    # Fork
    forked = agent.fork(name="forked")
    assert forked.yolo is True
    assert forked.allow_all is True

    # Restore on fresh agent
    fresh = TUIReActAgent(name="fresh", llm=llm)
    fresh._restore_extra_state(extra)
    assert fresh.yolo is True
    assert fresh.allow_all is True


@pytest.mark.asyncio
async def test_allow_all_bypasses_tool_approval():
    llm = MockLLM([
        LLMResponse(
            message=Message.assistant("", tool_calls=[
                ToolCall(id="tc1", name="unsafe_action", arguments={"command": "rm -rf /"})
            ]),
        ),
        LLMResponse(message=Message.assistant("Finished")),
    ])
    agent = TUIReActAgent(name="test", llm=llm, tools=[unsafe_action])

    called_approval = []
    async def mock_approval(tc):
        called_approval.append(tc.name)
        return "approve"

    agent.approval_callback = mock_approval

    # Normal mode: approval callback is invoked for unsafe_action
    await agent.chat("run unsafe")
    assert "unsafe_action" in called_approval

    # Reset agent & enable allow_all
    called_approval.clear()
    llm2 = MockLLM([
        LLMResponse(
            message=Message.assistant("", tool_calls=[
                ToolCall(id="tc2", name="unsafe_action", arguments={"command": "ls"})
            ]),
        ),
        LLMResponse(message=Message.assistant("Finished")),
    ])
    agent2 = TUIReActAgent(name="test2", llm=llm2, tools=[unsafe_action])
    agent2.approval_callback = mock_approval
    agent2.set_allow_all(True)

    await agent2.chat("run unsafe with allow_all")
    assert len(called_approval) == 0  # Bypassed approval callback!


@pytest.mark.asyncio
async def test_yolo_bypasses_tool_approval():
    called_approval = []
    async def mock_approval(tc):
        called_approval.append(tc.name)
        return "approve"

    llm = MockLLM([
        LLMResponse(
            message=Message.assistant("", tool_calls=[
                ToolCall(id="tc3", name="unsafe_action", arguments={"command": "pwd"})
            ]),
        ),
        LLMResponse(message=Message.assistant("Finished")),
    ])
    agent = TUIReActAgent(name="test3", llm=llm, tools=[unsafe_action])
    agent.approval_callback = mock_approval
    agent.set_yolo(True)

    await agent.chat("run unsafe with yolo")
    assert len(called_approval) == 0  # Bypassed approval callback!


@pytest.mark.asyncio
async def test_yolo_and_allow_all_commands_in_tui(tmp_path: Path):
    empty_sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent = TUIReActAgent(name="test", llm=MockLLM())
    app = Agent2App(agent=agent, session_manager=empty_sm)

    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        status = screen.query_one(StatusBar)

        # 1. /yolo on
        await screen._handle_command("/yolo on")
        assert agent.yolo is True
        assert status.yolo is True
        table_out = status.render()
        assert table_out is not None

        # 2. /yolo show (or /yolo)
        await screen._handle_command("/yolo")
        assert agent.yolo is True

        # 3. /yolo off
        await screen._handle_command("/yolo off")
        assert agent.yolo is False
        assert status.yolo is False

        # 4. /allow-all on
        await screen._handle_command("/allow-all on")
        assert agent.allow_all is True
        assert status.allow_all is True

        # 5. /allow-all (show)
        await screen._handle_command("/allow-all")
        assert agent.allow_all is True

        # 6. /allow-all off
        await screen._handle_command("/allow-all off")
        assert agent.allow_all is False
        assert status.allow_all is False

        # 7. /autopilot alias
        await screen._handle_command("/autopilot on")
        assert agent.yolo is True
        await screen._handle_command("/autopilot off")
        assert agent.yolo is False


@pytest.mark.asyncio
async def test_tab_navigation_across_top_buttons_and_panels(tmp_path: Path):
    empty_sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent = TUIReActAgent(name="test", llm=MockLLM())
    app = Agent2App(agent=agent, session_manager=empty_sm)

    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        top_bar = screen.query_one(TopTabBar)
        tab_current = screen.query_one("#tab-current", TabItem)
        tab_sessions = screen.query_one("#tab-sessions", TabItem)
        messages = screen.query_one("#messages", MessageList)
        chat_input = screen.query_one("#chat-input", ChatInput)

        # 1. On open, focus is on the first top button: tab-current
        assert app.focused == tab_current
        assert top_bar.active_tab == "current"

        # 2. Press Tab: switches to tab-sessions
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused == tab_sessions
        assert top_bar.active_tab == "sessions"

        # 3. When on sessions, press Tab again: switches to next panel (messages)
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused == messages

        # 4. Press Tab on messages: switches to next panel (chat-input)
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused == chat_input

        # 5. Press Tab on empty chat-input: wraps back to top buttons (tab-current)
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused == tab_current
        assert top_bar.active_tab == "current"

        # 6. Type-to-focus: typing a printable character while on tab-current redirects to chat-input
        await pilot.press("h")
        await pilot.pause()
        assert app.focused == chat_input
        assert "h" in chat_input.text
