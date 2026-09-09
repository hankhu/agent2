"""Tests for agent conversation compacting (/compact)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from agent2.agent.react import ReActAgent
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Role, Usage


class MockSummarizerLLM(BaseLLM):
    """Mock LLM for testing compaction."""

    def __init__(self) -> None:
        super().__init__(model="mock-model")
        self.compact_calls: list[list[Message]] = []

    async def chat(self, messages: list[Message], **kwargs) -> LLMResponse:
        self.compact_calls.append(messages)
        # Verify that summarizer prompt was supplied
        user_content = messages[-1].content or ""
        assert "Summarize the preceding conversation history" in user_content
        return LLMResponse(
            message=Message.assistant(
                "Summary: User asked to inspect codebase and run tests. Tests passed."
            ),
            usage=Usage(prompt_tokens=150, completion_tokens=50, total_tokens=200),
        )


@pytest.mark.asyncio
async def test_compact_skipped_when_history_too_short() -> None:
    mock_llm = MockSummarizerLLM()
    agent = ReActAgent("test_agent", llm=mock_llm)
    agent.set_rule("You are a helpful assistant.")

    # Only 1 turn
    agent._messages.append(Message.user("Hello!"))
    agent._messages.append(Message.assistant("Hi there!"))

    stats = await agent.compact(keep_recent_turns=1)
    assert stats["status"] == "skipped"
    assert stats["messages_before"] == len(agent._messages)
    assert len(mock_llm.compact_calls) == 0


@pytest.mark.asyncio
async def test_compact_compresses_earlier_turns_and_keeps_recent() -> None:
    mock_llm = MockSummarizerLLM()
    agent = ReActAgent("test_agent", llm=mock_llm)
    agent.set_rule("You are a helpful assistant.")

    # Turn 1
    agent._messages.append(Message.user("List files in the repo."))
    agent._messages.append(Message.assistant("Found 10 files."))

    # Turn 2
    agent._messages.append(Message.user("Run the tests."))
    agent._messages.append(Message.assistant("All tests passed."))

    # Turn 3 (most recent turn)
    agent._messages.append(Message.user("What is our next step?"))
    agent._messages.append(Message.assistant("Let's deploy."))

    assert len(agent._messages) == 7  # 1 system + 3 * (user + assistant)

    stats = await agent.compact(keep_recent_turns=1)
    assert stats["status"] == "compacted"
    assert stats["messages_before"] == 7
    # Structure after compact:
    # 0: System prompt
    # 1: User summary message
    # 2: Assistant acknowledgment
    # 3: Turn 3 User message
    # 4: Turn 3 Assistant message
    assert stats["messages_after"] == 5
    assert len(agent._messages) == 5

    assert agent._messages[0].role == Role.SYSTEM
    assert "Context Summary of Previous Conversation (compacted)" in (agent._messages[1].content or "")
    assert "Summary: User asked to inspect codebase" in (agent._messages[1].content or "")
    assert agent._messages[2].role == Role.ASSISTANT
    assert agent._messages[3].content == "What is our next step?"
    assert agent._messages[4].content == "Let's deploy."
