"""Tests for session conversation preview and session selection screen."""

from __future__ import annotations

from pathlib import Path
import pytest
from textual.widgets import OptionList, Static

from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.screens.session_select import SessionSelectScreen
from agent2.app.tui.session import SessionManager
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message


class DummyLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="dummy-model")

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        return LLMResponse(message=Message.assistant("Done"))


def test_session_manager_list_and_preview(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")

    agent_data = {
        "name": "assistant",
        "agent_type": "react",
        "messages": [
            {"role": "user", "content": "How do I implement OAuth2 authentication in FastAPI?"},
            {
                "role": "assistant",
                "content": "You can use fastapi.security OAuth2PasswordBearer.",
                "tool_calls": [{"name": "file_read", "arguments": {"path": "main.py"}}],
            },
            {
                "role": "tool",
                "tool_result": {"content": "from fastapi import FastAPI"},
            },
        ],
    }
    sm.save("sess_oauth", agent_data, title="OAuth2 Guide")

    # 1. Test list_sessions returns message_count and preview
    sessions = sm.list_sessions()
    assert len(sessions) == 1
    s0 = sessions[0]
    assert s0["id"] == "sess_oauth"
    assert s0["title"] == "OAuth2 Guide"
    assert s0["message_count"] == 3
    assert "OAuth2" in s0["preview"]

    # 2. Test get_session_preview
    preview = sm.get_session_preview("sess_oauth")
    assert "OAuth2 Guide" in preview
    assert "sess_oauth" in preview
    assert "3 messages" in preview
    assert "👤 User:" in preview
    assert "How do I implement OAuth2" in preview
    assert "🤖 Assistant:" in preview
    assert "OAuth2PasswordBearer" in preview
    assert "⚙ file_read" in preview


@pytest.mark.asyncio
async def test_session_select_screen_preview_and_delete(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")

    # Seed 2 sessions
    sm.save(
        "sess_1",
        {
            "messages": [
                {"role": "user", "content": "First conversation about database optimization"},
                {"role": "assistant", "content": "Let's index the foreign keys."},
            ]
        },
        title="DB Optimization",
    )
    sm.save(
        "sess_2",
        {
            "messages": [
                {"role": "user", "content": "Second conversation about CSS redesign"},
                {"role": "assistant", "content": "Let's use a modern dark theme."},
            ]
        },
        title="CSS Redesign",
    )

    sessions = sm.list_sessions()
    assert len(sessions) == 2

    screen = SessionSelectScreen(sessions=sessions, session_manager=sm)
    app = Agent2App(agent=TUIReActAgent(llm=DummyLLM()), session_manager=sm)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.app.push_screen(screen)
        await pilot.pause()

        # Check preview content displays highlighted session (sess_2, newest first)
        preview_w = screen.query_one("#session-preview-content", Static)
        assert "CSS Redesign" in preview_w.content or "Second conversation" in preview_w.content

        # Navigate down to sess_1
        opt_list = screen.query_one("#session-list", OptionList)
        await pilot.press("down")
        await pilot.pause()
        assert "DB Optimization" in preview_w.content or "First conversation" in preview_w.content

        # Delete requires the two-key sequence Ctrl+X, then X
        await pilot.press("ctrl+x")
        await pilot.pause()
        # A single X before arming should NOT delete
        assert len(sm.list_sessions()) == 2
        await pilot.press("x")
        await pilot.pause()

        # Verify sess_1 was deleted
        remaining = sm.list_sessions()
        assert len(remaining) == 1
        assert remaining[0]["id"] == "sess_2"
