"""Tests for multi-scope approval functionality (once, conversation, project, always)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import Button

from agent2.app.approval import (
    get_global_approvals_path,
    get_project_approvals_path,
    is_tool_approved,
    load_approved_tools,
    record_approval,
    save_approved_tool,
)
from agent2.app.tui.app import Agent2App, TUIReActAgent, restore_agent
from agent2.app.tui.session import SessionManager
from agent2.app.tui.widgets.confirm_modal import ConfirmCard
from agent2.app.tui.widgets.message_list import MessageList
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message
from agent2.tools.base import tool


class DummyLLM(BaseLLM):
    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        super().__init__(model="dummy-model")
        self._responses = list(responses or [])
        self._idx = 0

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        if self._idx < len(self._responses):
            res = self._responses[self._idx]
            self._idx += 1
            return res
        return LLMResponse(message=Message.assistant("Done"))


@tool(name="risky_tool", description="A tool that requires approval")
def risky_tool(action: str) -> str:
    return f"Executed {action}"


def test_approval_helper_persistence(tmp_path: Path) -> None:
    # 1. Initially empty
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()
    proj_approvals = proj_dir / ".agent2" / "approvals.json"

    glob_dir = tmp_path / "global"
    glob_dir.mkdir()
    glob_approvals = glob_dir / "approvals.json"

    conv_set: set[str] = set()

    with patch("agent2.app.approval.get_project_approvals_path", return_value=proj_approvals), \
         patch("agent2.app.approval.get_global_approvals_path", return_value=glob_approvals):

        assert not is_tool_approved("risky_tool", conv_set, cwd=proj_dir)

        # 2. approve once: not persisted anywhere
        record_approval("risky_tool", "approve_once", conv_set, cwd=proj_dir)
        assert not is_tool_approved("risky_tool", conv_set, cwd=proj_dir)
        assert not proj_approvals.exists()
        assert not glob_approvals.exists()

        # 3. approve in conversation: only in conv_set
        record_approval("risky_tool", "approve_conversation", conv_set, cwd=proj_dir)
        assert is_tool_approved("risky_tool", conv_set, cwd=proj_dir)
        assert not proj_approvals.exists()
        assert not glob_approvals.exists()

        # 4. Clear conv_set, approve in project
        conv_set.clear()
        assert not is_tool_approved("project_tool", conv_set, cwd=proj_dir)
        record_approval("project_tool", "approve_project", conv_set, cwd=proj_dir)
        assert "project_tool" in conv_set
        assert is_tool_approved("project_tool", conv_set, cwd=proj_dir)
        assert proj_approvals.exists()
        assert "project_tool" in load_approved_tools(proj_approvals)
        assert not glob_approvals.exists()

        # 5. Approve always (global)
        conv_set.clear()
        assert not is_tool_approved("global_tool", conv_set, cwd=proj_dir)
        record_approval("global_tool", "always", conv_set, cwd=proj_dir)
        assert "global_tool" in conv_set
        assert is_tool_approved("global_tool", conv_set, cwd=proj_dir)
        assert glob_approvals.exists()
        assert "global_tool" in load_approved_tools(glob_approvals)


@pytest.mark.asyncio
async def test_tui_agent_approval_scopes_execution(tmp_path: Path) -> None:
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    proj_approvals = proj_dir / ".agent2" / "approvals.json"
    glob_approvals = tmp_path / "global_approvals.json"

    with patch("agent2.app.approval.get_project_approvals_path", return_value=proj_approvals), \
         patch("agent2.app.approval.get_global_approvals_path", return_value=glob_approvals):

        agent = TUIReActAgent(
            llm=DummyLLM(),
            tools=[risky_tool],
        )

        approval_calls = []

        async def mock_approval(tc):
            approval_calls.append(tc.name)
            return "approve_once"

        agent.approval_callback = mock_approval

        # Call 1: approve once
        class MockTC:
            id = "call_1"
            name = "risky_tool"
            arguments = {"action": "first"}

        results = await agent._execute_tool_calls([MockTC()])
        assert len(approval_calls) == 1
        assert "Executed first" in results[0].tool_result.content

        # Call 2: since it was approve once, it must ask again!
        class MockTC2:
            id = "call_2"
            name = "risky_tool"
            arguments = {"action": "second"}

        results2 = await agent._execute_tool_calls([MockTC2()])
        assert len(approval_calls) == 2  # prompted again!

        # Call 3: approve in conversation
        async def mock_approval_conv(tc):
            approval_calls.append(tc.name)
            return "approve_conversation"

        agent.approval_callback = mock_approval_conv
        await agent._execute_tool_calls([MockTC()])
        assert len(approval_calls) == 3

        # Call 4: should NOT ask approval now
        await agent._execute_tool_calls([MockTC()])
        assert len(approval_calls) == 3  # not called!


@pytest.mark.asyncio
async def test_confirm_card_keyboard_shortcuts_all_scopes() -> None:
    decisions = []

    def on_decision(val: str) -> None:
        decisions.append(val)

    app = Agent2App(agent=TUIReActAgent(llm=DummyLLM(), tools=[risky_tool]))
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # 1. Shortcut '1' -> approve_once
        messages.add_confirm_card("risky_tool", {"action": "test"}, on_decision=on_decision)
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert decisions[-1] == "approve_once"

        # 2. Shortcut 'c' -> approve_conversation
        messages.add_confirm_card("risky_tool", {"action": "test"}, on_decision=on_decision)
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert decisions[-1] == "approve_conversation"

        # 3. Shortcut 'p' -> approve_project
        messages.add_confirm_card("risky_tool", {"action": "test"}, on_decision=on_decision)
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert decisions[-1] == "approve_project"

        # 4. Shortcut 'a' -> always
        messages.add_confirm_card("risky_tool", {"action": "test"}, on_decision=on_decision)
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert decisions[-1] == "always"

        # 5. Shortcut 'escape' -> reject
        messages.add_confirm_card("risky_tool", {"action": "test"}, on_decision=on_decision)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert decisions[-1] == "reject"


def test_agent_auto_approved_restoration(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent = TUIReActAgent(llm=DummyLLM(), tools=[risky_tool])
    agent._auto_approved = {"tool_a", "tool_b"}

    data = agent.to_dict()
    assert "auto_approved" in data["extra"]
    assert set(data["extra"]["auto_approved"]) == {"tool_a", "tool_b"}

    sm.save("sess_test", data, title="Test Session")

    # Restore into fresh agent
    new_agent = TUIReActAgent(llm=DummyLLM(), tools=[risky_tool])
    assert new_agent._auto_approved == set()

    restore_agent(new_agent, sm, "sess_test")
    assert new_agent._auto_approved == {"tool_a", "tool_b"}

