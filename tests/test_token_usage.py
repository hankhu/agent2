"""Tests for session token usage persistence, live updates, and plan aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent2.app.tui.app import Agent2App, TUIReActAgent, restore_agent
from agent2.app.tui.planner import Plan, TaskItem
from agent2.app.tui.screens.chat import ChatScreen, ThoughtReceived
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.status_bar import ContextBar
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Usage


class DummyLLM(BaseLLM):
    """Minimal LLM implementation for TUI tests."""

    def __init__(self, model: str = "dummy-model") -> None:
        super().__init__(model=model)

    async def chat(self, messages: list[Message], *, tools: Any = None, **kwargs: Any) -> LLMResponse:
        return LLMResponse(message=Message.assistant("Dummy response"))


@pytest.mark.asyncio
async def test_thought_event_updates_context_bar_live(tmp_path: Path) -> None:
    """Token usage is pushed to the ContextBar as soon as a thought arrives."""
    agent = TUIReActAgent(name="assistant", llm=DummyLLM())
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, ChatScreen)
        context_bar = screen.query_one(ContextBar)
        assert context_bar.input_tokens == 0
        assert context_bar.output_tokens == 0

        # Simulate an LLM call having just completed and posted a thought event.
        agent.llm.total_usage = Usage(prompt_tokens=120, completion_tokens=30, total_tokens=150)
        screen.on_thought_received(ThoughtReceived("thinking...", 1))
        await pilot.pause()

        assert context_bar.input_tokens == 120
        assert context_bar.output_tokens == 30


def test_usage_persisted_across_session_save_and_restore(tmp_path: Path) -> None:
    """Session save writes usage and restore reads it back into the agent."""
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent = TUIReActAgent(name="assistant", llm=DummyLLM("original-model"))
    agent._messages = [Message.user("Hello"), Message.assistant("Hi there")]
    agent.llm.total_usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

    sm.save("usage_sess", agent.to_dict(), title="Usage Session")
    data = sm.load("usage_sess")
    assert data["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }

    restored_agent = TUIReActAgent(name="assistant", llm=DummyLLM("new-model"))
    # Put a stale counter on the target LLM to prove restore overwrites it.
    restored_agent.llm.total_usage = Usage(prompt_tokens=999, completion_tokens=999, total_tokens=1998)
    restore_agent(restored_agent, sm, "usage_sess")

    assert restored_agent.llm.total_usage.total_tokens == 150
    assert restored_agent.llm.total_usage.prompt_tokens == 100
    assert restored_agent.llm.total_usage.completion_tokens == 50


def test_restore_legacy_session_estimates_usage(tmp_path: Path) -> None:
    """Legacy sessions without a usage field get a best-effort estimate."""
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    legacy = {
        "agent_type": "TUIReActAgent",
        "name": "assistant",
        "system_prompt": "sys",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I am fine, thank you."},
            {"role": "user", "content": "What is two plus two?"},
            {"role": "assistant", "content": "Two plus two is four."},
        ],
    }
    sm.save("legacy_sess", legacy, title="Legacy")

    agent = TUIReActAgent(name="assistant", llm=DummyLLM())
    # Stale live usage must not leak into a legacy session restore.
    agent.llm.total_usage = Usage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    restore_agent(agent, sm, "legacy_sess")

    assert agent.llm.total_usage.total_tokens > 0
    assert agent.llm.total_usage.total_tokens != 1000


def test_switch_model_preserves_usage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Switching models keeps accumulated and last usage counters."""
    agent = TUIReActAgent(name="assistant", llm=DummyLLM("old-model"))
    agent.llm.total_usage = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    agent.llm.last_usage = Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    new_llm = DummyLLM("new-model")
    monkeypatch.setattr("agent2.app.tui.app.create_llm", lambda model: new_llm)
    monkeypatch.setattr("agent2.app.tui.app.set_last_model", lambda model: None)

    app.switch_model("new-model")

    assert app.agent.llm is new_llm
    assert app.agent.llm.total_usage == Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    assert app.agent.llm.last_usage == Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3)


@pytest.mark.asyncio
async def test_plan_subagent_usage_aggregated_into_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Plan execution adds every subtask's LLM usage to the parent session total."""
    agent = TUIReActAgent(name="main-agent", llm=DummyLLM())
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)

    plan = Plan(
        goal="Complete two steps",
        summary="Two-step plan",
        tasks=[
            TaskItem(id="1", description="First step"),
            TaskItem(id="2", description="Second step", dependencies=["1"]),
        ],
    )

    created_subagents: list[Any] = []

    class FakeSubagent:
        def __init__(self) -> None:
            self.llm = DummyLLM()
            self.llm.total_usage = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            self.run = AsyncMock(return_value="subtask result")
            self.log = None
            self.approval_callback = None

    def fake_build_tui_agent(**kwargs: Any) -> FakeSubagent:
        subagent = FakeSubagent()
        created_subagents.append(subagent)
        return subagent

    async def fake_synthesize_plan_results(
        llm: BaseLLM,
        *,
        goal: str,
        task_results: list[dict[str, Any]],
    ) -> str:
        return "final synthesized answer"

    monkeypatch.setattr("agent2.app.tui.app.build_tui_agent", fake_build_tui_agent)
    monkeypatch.setattr(
        "agent2.app.tui.screens.chat.synthesize_plan_results",
        fake_synthesize_plan_results,
    )

    async with app.run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, ChatScreen)

        # Call the original coroutine behind Textual's @work decorator so the
        # test remains deterministic while still exercising the real method.
        await ChatScreen._run_plan_execution.__wrapped__(screen, plan, "Complete two steps")
        await pilot.pause()

        assert len(created_subagents) == 2
        assert app.agent.llm.total_usage.total_tokens == 60
        assert app.agent.llm.total_usage.prompt_tokens == 20
        assert app.agent.llm.total_usage.completion_tokens == 40

        context_bar = screen.query_one(ContextBar)
        assert context_bar.input_tokens == 20
        assert context_bar.output_tokens == 40


@pytest.mark.asyncio
async def test_ui_resume_restores_usage_without_resetting(tmp_path: Path) -> None:
    """The /resume UI path restores persisted usage instead of zeroing it."""
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")

    saved_agent = TUIReActAgent(name="assistant", llm=DummyLLM("saved-model"))
    saved_agent._messages = [Message.user("Old question"), Message.assistant("Old answer")]
    saved_agent.llm.total_usage = Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
    sm.save("ui_resume", saved_agent.to_dict(), title="UI Resume")

    agent = TUIReActAgent(name="assistant", llm=DummyLLM("current-model"))
    agent.llm.total_usage = Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
    app = Agent2App(agent=agent, session_manager=sm)

    async with app.run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, ChatScreen)

        screen._handle_resume("ui_resume")
        await pilot.pause()

        assert app.agent.llm.total_usage.total_tokens == 300
        context_bar = screen.query_one(ContextBar)
        assert context_bar.input_tokens == 200
        assert context_bar.output_tokens == 100


@pytest.mark.asyncio
async def test_failed_plan_subtask_usage_is_still_aggregated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Tokens consumed before a subtask error are not lost from the session total."""
    agent = TUIReActAgent(name="main-agent", llm=DummyLLM())
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(agent=agent, session_manager=sm)
    plan = Plan(goal="One failing step", tasks=[TaskItem(id="1", description="Fails")])

    class FailingSubagent:
        def __init__(self) -> None:
            self.llm = DummyLLM()
            self.llm.total_usage = Usage(prompt_tokens=7, completion_tokens=8, total_tokens=15)
            self.run = AsyncMock(side_effect=RuntimeError("subtask failed"))
            self.log = None
            self.approval_callback = None

    monkeypatch.setattr(
        "agent2.app.tui.app.build_tui_agent",
        lambda **kwargs: FailingSubagent(),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, ChatScreen)

        await ChatScreen._run_plan_execution.__wrapped__(screen, plan, "One failing step")
        await pilot.pause()

        assert app.agent.llm.total_usage.total_tokens == 15
        context_bar = screen.query_one(ContextBar)
        assert context_bar.input_tokens == 7
        assert context_bar.output_tokens == 8
