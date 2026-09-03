"""Comprehensive tests for /rewind, /fork, and point selection in history messages."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button

from agent2.agent.base import BaseAgent
from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import AssistantMessage, MessageList, UserMessage
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Role


class MockLLM(BaseLLM):
    """Mock LLM for testing conversation turns."""

    def __init__(self, responses: list[str] | None = None) -> None:
        super().__init__(model="mock-model")
        self._responses = list(responses or [])

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        if self._responses:
            resp = self._responses.pop(0)
            return LLMResponse(message=Message.assistant(resp))
        return LLMResponse(message=Message.assistant(f"Response #{len(messages)}"))


# ── 1. Core BaseAgent Rewind & Rewind_To Tests ───────────────────


def test_base_agent_rewind_turns() -> None:
    from agent2.agent.react import ReActAgent

    agent = ReActAgent(name="test", system_prompt="System instructions", llm=MockLLM())
    agent._messages = [
        Message.system("System instructions"),
        Message.user("Question 1"),
        Message.assistant("Answer 1"),
        Message.user("Question 2"),
        Message.assistant("Answer 2"),
    ]

    # Rewind 1 turn
    removed = agent.rewind(1)
    assert len(removed) == 2
    assert removed[0].content == "Question 2"
    assert removed[1].content == "Answer 2"
    assert len(agent.messages) == 3
    assert agent.messages[-1].content == "Answer 1"

    # Rewind another turn
    removed2 = agent.rewind(1)
    assert len(removed2) == 2
    assert removed2[0].content == "Question 1"
    assert len(agent.messages) == 1
    assert agent.messages[0].role == Role.SYSTEM

    # Rewind when no turns left
    removed3 = agent.rewind(1)
    assert removed3 == []
    assert len(agent.messages) == 1


def test_base_agent_rewind_to() -> None:
    from agent2.agent.react import ReActAgent

    agent = ReActAgent(name="test", system_prompt="System", llm=MockLLM())
    agent._messages = [
        Message.system("System"),
        Message.user("Q1"),       # index 1
        Message.assistant("A1"),  # index 2
        Message.user("Q2"),       # index 3
        Message.assistant("A2"),  # index 4
    ]

    # Rewind to Q2 (exclusive: removes Q2 and after)
    removed = agent.rewind_to(3, inclusive=False)
    assert len(removed) == 2
    assert [m.content for m in removed] == ["Q2", "A2"]
    assert len(agent.messages) == 3
    assert [m.content for m in agent.messages] == ["System", "Q1", "A1"]

    # Rewind to A1 (inclusive: keeps A1, would remove after it)
    agent._messages = [
        Message.system("System"),
        Message.user("Q1"),       # 1
        Message.assistant("A1"),  # 2
        Message.user("Q2"),       # 3
        Message.assistant("A2"),  # 4
    ]
    removed2 = agent.rewind_to(2, inclusive=True)
    assert len(removed2) == 2
    assert [m.content for m in removed2] == ["Q2", "A2"]
    assert len(agent.messages) == 3
    assert agent.messages[-1].content == "A1"


# ── 2. TUIReActAgent Fork Isolation Test ────────────────────────


def test_tui_react_agent_fork_isolation() -> None:
    agent = TUIReActAgent(name="parent", llm=MockLLM(), mode="ask")
    agent._auto_approved.add("test_tool")
    agent._messages.append(Message.user("Hello"))

    forked = agent.fork("child")
    assert forked.name == "child"
    assert forked.mode == "ask"
    assert "test_tool" in forked._auto_approved
    assert len(forked.messages) == 1

    # Mutating child doesn't affect parent
    forked._auto_approved.add("new_tool")
    forked._messages.append(Message.assistant("World"))
    assert "new_tool" not in agent._auto_approved
    assert len(agent.messages) == 1


# ── 3. Slash Command /rewind Test ───────────────────────────────


@pytest.mark.asyncio
async def test_slash_command_rewind(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("First question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Second question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Check 2 user messages present
        user_msgs = list(messages.query(UserMessage))
        assert len(user_msgs) == 2

        # Issue /rewind command
        chat_input.clear()
        chat_input.insert("/rewind")
        await pilot.press("enter")
        await pilot.pause()

        # Only Turn 1 remains
        user_msgs_after = list(messages.query(UserMessage))
        assert len(user_msgs_after) == 1
        assert user_msgs_after[0]._text == "First question"

        # Chat input has the rewound prompt restored
        assert chat_input.text.strip() == "Second question"


# ── 4. Slash Command /fork Test ─────────────────────────────────


@pytest.mark.asyncio
async def test_slash_command_fork(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2 in fork"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Initial turn
        chat_input.clear()
        chat_input.insert("Initial question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        orig_session_id = app.session_id

        # Issue /fork command
        chat_input.clear()
        chat_input.insert("/fork Cloned Branch")
        await pilot.press("enter")
        await pilot.pause()

        # Session ID changed and title updated
        assert app.session_id != orig_session_id
        assert app.session_title == "Cloned Branch"

        # Continue chatting in the forked session
        chat_input.clear()
        chat_input.insert("Question in forked branch")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Verify original session file has 1 turn
        orig_data = sm.load(orig_session_id)
        assert len([m for m in orig_data["agent"]["messages"] if m.get("role") == "user"]) == 1

        # Verify new session file has 2 turns
        forked_data = sm.load(app.session_id)
        assert len([m for m in forked_data["agent"]["messages"] if m.get("role") == "user"]) == 2
        assert forked_data["title"] == "Cloned Branch"


# ── 5. Message Selection & Action Buttons Visibility Test ───────


@pytest.mark.asyncio
async def test_message_selection_and_action_buttons_visibility(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        chat_input.clear()
        chat_input.insert("Msg 1")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        u_msg = messages.query_one(UserMessage)
        a_msg = messages.query_one(AssistantMessage)

        # 1. Initially, buttons are not displayed (hidden)
        u_actions = u_msg.query_one(".message-actions")
        a_actions = a_msg.query_one(".message-actions")
        assert not u_actions.display
        assert not a_actions.display

        # 2. Click UserMessage -> becomes selected, actions shown
        await pilot.click(u_msg)
        await pilot.pause()
        assert "selected" in u_msg.classes
        assert u_actions.display
        assert not a_actions.display

        # 3. Click AssistantMessage -> UserMessage deselected, AssistantMessage selected
        await pilot.click(a_msg)
        await pilot.pause()
        assert "selected" not in u_msg.classes
        assert "selected" in a_msg.classes
        assert not u_actions.display
        assert a_actions.display

        # 4. Press Escape -> deselects all, hides actions, refocuses chat_input
        await pilot.press("escape")
        await pilot.pause()
        assert "selected" not in a_msg.classes
        assert not a_actions.display
        assert chat_input.has_focus


# ── 6. Point Rewind from UserMessage Test ────────────────────────


@pytest.mark.asyncio
async def test_point_rewind_from_user_message(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("First question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Second question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        user_msgs = list(messages.query(UserMessage))
        assert len(user_msgs) == 2
        u2 = user_msgs[1]

        # Select Turn 2's UserMessage
        await pilot.click(u2)
        await pilot.pause()
        assert "selected" in u2.classes

        # Click Rewind button on u2
        btn_rewind = u2.query_one(".btn-rewind", Button)
        await pilot.click(btn_rewind)
        await pilot.pause()

        # Only Turn 1 remains in UI and agent
        user_msgs_after = list(messages.query(UserMessage))
        assert len(user_msgs_after) == 1
        assert user_msgs_after[0]._text == "First question"

        # Turn 2 user text restored to chat input
        assert chat_input.text.strip() == "Second question"


# ── 7. Point Rewind from AssistantMessage Test ───────────────────


@pytest.mark.asyncio
async def test_point_rewind_from_assistant_message(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(100, 60)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("First question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Second question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        asst_msgs = list(messages.query(AssistantMessage))
        assert len(asst_msgs) == 2
        a1 = asst_msgs[0]

        # Select Turn 1's AssistantMessage
        a1.scroll_visible()
        await pilot.pause()
        await pilot.click(a1)
        await pilot.pause()
        assert "selected" in a1.classes

        # Click Rewind on Turn 1's AssistantMessage
        btn_rewind = a1.query_one(".btn-rewind", Button)
        await pilot.click(btn_rewind)
        await pilot.pause()

        # Turn 2 removed, Turn 1 AssistantMessage preserved
        asst_msgs_after = list(messages.query(AssistantMessage))
        assert len(asst_msgs_after) == 1
        assert asst_msgs_after[0]._content == "Answer 1"
        assert len([m for m in app.agent.messages if m.role == Role.USER]) == 1


# ── 8. Point Fork from UserMessage Test ──────────────────────────


@pytest.mark.asyncio
async def test_point_fork_from_user_message(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(100, 60)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("First question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Second question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        orig_id = app.session_id
        user_msgs = list(messages.query(UserMessage))
        u2 = user_msgs[1]

        # Click u2 to select
        u2.scroll_visible()
        await pilot.pause()
        await pilot.click(u2)
        await pilot.pause()

        # Click Fork button on u2
        btn_fork = u2.query_one(".btn-fork", Button)
        await pilot.click(btn_fork)
        await pilot.pause()

        # Session cloned into new session
        assert app.session_id != orig_id

        # Cloned session contains only Turn 1 history
        assert len([m for m in app.agent.messages if m.role == Role.USER]) == 1

        # Turn 2's user prompt is placed into chat input
        assert chat_input.text.strip() == "Second question"


# ── 9. Point Fork from AssistantMessage Test ─────────────────────


@pytest.mark.asyncio
async def test_point_fork_from_assistant_message(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(100, 60)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("First question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Second question")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        orig_id = app.session_id
        asst_msgs = list(messages.query(AssistantMessage))
        a1 = asst_msgs[0]

        # Select a1
        a1.scroll_visible()
        await pilot.pause()
        await pilot.click(a1)
        await pilot.pause()

        # Click Fork button on a1
        btn_fork = a1.query_one(".btn-fork", Button)
        await pilot.click(btn_fork)
        await pilot.pause()

        # Session cloned into new session
        assert app.session_id != orig_id

        # Cloned session contains Turn 1 (both user and assistant)
        assert len([m for m in app.agent.messages if m.role == Role.USER]) == 1
        assert len([m for m in app.agent.messages if m.role == Role.ASSISTANT]) == 1
        assert app.agent.messages[-1].content == "Answer 1"
