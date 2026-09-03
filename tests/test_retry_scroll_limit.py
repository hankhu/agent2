"""Comprehensive tests for:
1. /retry command and RetryRequested buttons
2. Sticky auto-scrolling on new messages (respecting user manual scrolling)
3. Collapsible folding for written code blocks and large text paragraphs
4. Multi-turn max iterations continuation (/continue and approval continuation)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Collapsible, Markdown

from agent2.agent.base import MaxIterationsExceeded
from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.confirm_modal import ConfirmCard
from agent2.app.tui.widgets.diff_view import DiffView
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import (
    AssistantMessage,
    ContinueRequested,
    MessageList,
    RetryRequested,
    UserMessage,
)
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Role, ToolCall
from agent2.tools.base import Tool


class MockLLM(BaseLLM):
    """Mock LLM for simulating responses."""

    def __init__(self, responses: list[str | LLMResponse] | None = None) -> None:
        super().__init__(model="mock-model")
        self._responses = list(responses or [])

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        if self._responses:
            item = self._responses.pop(0)
            if isinstance(item, LLMResponse):
                return item
            return LLMResponse(message=Message.assistant(item))
        return LLMResponse(message=Message.assistant(f"Echo turn {len(messages)}"))


# ── 1. Slash Command /retry Tests ──────────────────────────────


@pytest.mark.asyncio
async def test_slash_command_retry(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2 initial", "Answer 2 retried"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("Q1")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Q2")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assistants = list(messages.query(AssistantMessage))
        assert len(assistants) == 2
        assert assistants[-1]._content == "Answer 2 initial"

        # Issue /retry
        chat_input.clear()
        chat_input.insert("/retry")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assistants_after = list(messages.query(AssistantMessage))
        assert len(assistants_after) == 2
        assert assistants_after[-1]._content == "Answer 2 retried"


# ── 2. Message Action Button Retry Tests ───────────────────────


@pytest.mark.asyncio
async def test_point_retry_on_user_message(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer 2", "Answer 1 regenerated"])
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

        # Select first UserMessage and click Retry
        first_user = user_msgs[0]
        first_user.select()
        retry_btn = first_user.query_one(".btn-retry", Button)
        retry_btn.press()
        await pilot.pause()
        await pilot.pause()

        # Should have rewound back to Turn 1 and regenerated
        user_msgs_after = list(messages.query(UserMessage))
        assert len(user_msgs_after) == 1
        assert user_msgs_after[0]._text == "First question"
        assistant_msgs_after = list(messages.query(AssistantMessage))
        assert len(assistant_msgs_after) == 1
        assert assistant_msgs_after[0]._content == "Answer 1 regenerated"


@pytest.mark.asyncio
async def test_point_retry_on_assistant_message(tmp_path: Path) -> None:
    llm = MockLLM(["A1", "A2 original", "A2 regenerated"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("Q1")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Turn 2
        chat_input.clear()
        chat_input.insert("Q2")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assistants = list(messages.query(AssistantMessage))
        assert len(assistants) == 2

        # Click retry on the second assistant response
        second_assistant = assistants[1]
        second_assistant.select()
        retry_btn = second_assistant.query_one(".btn-retry", Button)
        retry_btn.press()
        await pilot.pause()
        await pilot.pause()

        assistants_after = list(messages.query(AssistantMessage))
        assert len(assistants_after) == 2
        assert assistants_after[1]._content == "A2 regenerated"


# ── 3. Sticky Auto-Scroll Logic Tests ──────────────────────────


def test_message_list_sticky_scroll_behavior() -> None:
    msg_list = MessageList()
    msg_list._anchored = True
    msg_list._anchor_released = False

    # When user hasn't touched scrollbar (_anchor_released is False)
    scrolled = []

    def mock_scroll_end(animate=False):
        scrolled.append(True)

    msg_list.scroll_end = mock_scroll_end

    msg_list._maybe_scroll_to_bottom()
    assert len(scrolled) == 1

    # Simulate user scrolling up (releasing anchor)
    msg_list._anchor_released = True
    # Overriding is_vertical_scroll_end property
    type(msg_list).is_vertical_scroll_end = property(lambda self: False)

    scrolled.clear()
    msg_list._maybe_scroll_to_bottom()
    # Should NOT scroll because user actively moved away
    assert len(scrolled) == 0

    # User adds a new message -> anchor resets and scrolls down
    # Calling add_user_message mounts a message and re-anchors
    # We test the re-anchoring logic directly:
    msg_list._anchor_released = False
    msg_list._maybe_scroll_to_bottom()
    assert len(scrolled) == 1


# ── 4. Content Folding Tests ───────────────────────────────────


def test_assistant_message_folding_code_and_large_text() -> None:
    # Short response: no Collapsible
    short_msg = AssistantMessage("Hello world! This is a simple reply.")
    short_collapsibles = list(short_msg._compose_content())
    assert not any(isinstance(w, Collapsible) for w in short_collapsibles)

    # Long code block (>= 4 lines): folded
    code_content = (
        "Here is the code:\n\n"
        "```python\n"
        "def add(a, b):\n"
        "    result = a + b\n"
        "    print(result)\n"
        "    return result\n"
        "```\n"
    )
    code_msg = AssistantMessage(code_content)
    widgets = list(code_msg._compose_content())
    collapsibles = [w for w in widgets if isinstance(w, Collapsible)]
    assert len(collapsibles) == 1
    assert "Code" in collapsibles[0].title

    # Large text block (>= 8 lines): folded
    long_text = "\n".join(f"Paragraph line {i} explaining complex concepts in detail." for i in range(12))
    text_msg = AssistantMessage(long_text)
    text_widgets = list(text_msg._compose_content())
    text_collapsibles = [w for w in text_widgets if isinstance(w, Collapsible)]
    assert len(text_collapsibles) == 1
    assert "Text" in text_collapsibles[0].title


@pytest.mark.asyncio
async def test_confirm_card_diff_folding() -> None:
    from textual.app import App

    class TestApp(App):
        def compose(self):
            card_short = ConfirmCard("file_write", {"path": "short.py", "content": "print(1)"})
            card_short._compute_diff = lambda: "line1\nline2\nline3"
            yield card_short

            card_large = ConfirmCard("file_write", {"path": "large.py", "content": "..."})
            card_large._compute_diff = lambda: "\n".join(f"+line {i}" for i in range(10))
            yield card_large

    app = TestApp()
    async with app.run_test():
        cards = list(app.screen.query(ConfirmCard))
        assert len(cards) == 2
        # First card has short diff -> DiffView is mounted, no Collapsible
        assert any(isinstance(w, DiffView) for w in cards[0].children)
        assert not any(isinstance(w, Collapsible) for w in cards[0].children)

        # Second card has large diff -> DiffView wrapped inside Collapsible
        collapsibles = [w for w in cards[1].children if isinstance(w, Collapsible)]
        assert len(collapsibles) == 1
        assert "Diff" in collapsibles[0].title


# ── 5. Max Iterations Continuation Tests ────────────────────────


@pytest.mark.asyncio
async def test_tui_react_agent_max_iterations_prompt_and_continue() -> None:
    def dummy_tool_fn() -> str:
        return "tool done"

    dummy_tool = Tool(dummy_tool_fn, name="dummy")

    # Simulate LLM wanting to call tools continuously
    tc = ToolCall(id="tc_1", name="dummy", arguments={})
    tool_resp = LLMResponse(message=Message(role=Role.ASSISTANT, tool_calls=[tc]))
    final_resp = LLMResponse(message=Message(role=Role.ASSISTANT, content="Done!"))

    # Agent with max_iterations=2
    llm = MockLLM([tool_resp, tool_resp, final_resp])
    agent = TUIReActAgent(name="test_agent", llm=llm, tools=[dummy_tool], max_iterations=2)

    prompt_rounds = []

    async def mock_approval(tool_call) -> str:
        if tool_call.name == "max_iterations":
            prompt_rounds.append(tool_call.arguments.get("rounds"))
            return "approve"  # Allow continuing
        return "approve"

    agent.approval_callback = mock_approval
    agent._auto_approved.add("dummy")

    res = await agent.run("Perform multi-step task")
    assert res == "Done!"
    # Reached 2 iterations, asked for continuation, approved, completed on 3rd
    assert prompt_rounds == [2]


@pytest.mark.asyncio
async def test_tui_react_agent_max_iterations_rejected() -> None:
    def dummy_tool_fn() -> str:
        return "tool done"

    dummy_tool = Tool(dummy_tool_fn, name="dummy")
    tc = ToolCall(id="tc_1", name="dummy", arguments={})
    tool_resp = LLMResponse(message=Message(role=Role.ASSISTANT, tool_calls=[tc]))

    llm = MockLLM([tool_resp, tool_resp, tool_resp])
    agent = TUIReActAgent(name="test_agent", llm=llm, tools=[dummy_tool], max_iterations=2)

    async def mock_approval(tool_call) -> str:
        if tool_call.name == "max_iterations":
            return "reject"  # User stops
        return "approve"

    agent.approval_callback = mock_approval
    agent._auto_approved.add("dummy")

    # When rejected, agent.chat() catches MaxIterationsExceeded and returns summary
    res = await agent.chat("Perform task")
    assert "unable to complete the task within 2 steps" in res


@pytest.mark.asyncio
async def test_slash_command_continue(tmp_path: Path) -> None:
    llm = MockLLM(["Answer 1", "Answer continued"])
    agent = TUIReActAgent(name="agent", llm=llm)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # Turn 1
        chat_input.clear()
        chat_input.insert("Initial task")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Issue /continue
        chat_input.clear()
        chat_input.insert("/continue")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        user_msgs = list(messages.query(UserMessage))
        assert len(user_msgs) == 2
        assert "请继续完成上述任务" in user_msgs[1]._text
        assistants = list(messages.query(AssistantMessage))
        assert len(assistants) == 2
        assert assistants[1]._content == "Answer continued"
