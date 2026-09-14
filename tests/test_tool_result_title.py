"""Tests for tool card collapsible title showing the first line of the command."""

from __future__ import annotations

import pytest
from textual.widgets import Collapsible

from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.widgets.message_list import MessageList
from agent2.app.tui.widgets.tool_card import ToolCard
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message


class DummyLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="dummy-model")

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        return LLMResponse(message=Message.assistant("Done"))


def test_tool_card_result_title_extraction() -> None:
    # 1. Shell command with multiple lines
    card1 = ToolCard(
        "shell_exec",
        {"command": "pytest tests/test_tui.py -v\necho done\nls -la"},
    )
    assert card1._get_result_title() == "Result: pytest tests/test_tui.py -v"

    # 2. Python code with multiple lines
    card2 = ToolCard(
        "python_exec",
        {"code": "import sys\nprint(sys.version)"},
    )
    assert card2._get_result_title() == "Result: import sys"

    # 3. File ops with path
    card3 = ToolCard(
        "file_read",
        {"path": "src/agent2/app.py"},
    )
    assert card3._get_result_title() == "Result: file_read src/agent2/app.py"

    # 4. Web search with query
    card4 = ToolCard(
        "web_search",
        {"query": "python textual framework"},
    )
    assert card4._get_result_title() == "Result: web_search python textual framework"

    # 5. Fallback tool
    card5 = ToolCard("custom_tool", {})
    assert card5._get_result_title() == "Result: custom_tool"


@pytest.mark.asyncio
async def test_tool_card_collapsible_mount_and_set_result() -> None:
    from agent2.app.tui.widgets.tool_card import ToolTitle

    app = Agent2App(agent=TUIReActAgent(llm=DummyLLM()))
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)

        # 1. Mount card (initially running)
        card = messages.add_tool_card("shell_exec", {"command": "git status\ngit diff"})
        await pilot.pause()

        result_w = card.query_one(".tool-result", Collapsible)
        title_w = result_w.query_one(ToolTitle)
        assert title_w.running is True
        # No extra status line while running or on success
        assert len(card.query("#tool-status")) == 0

        # 2. Complete with success
        card.set_result("On branch main\nnothing to commit", is_error=False)
        await pilot.pause()

        assert "Exec:" in result_w.title or "shell_exec" in result_w.title
        assert result_w.collapsed is True
        assert title_w.running is False
        # Success: success|fail+"Result" omitted, no additional line!
        assert len(card.query("#tool-status")) == 0

        # 3. Ctrl+O expands result
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert result_w.collapsed is False

        # 4. Another card with error
        card_err = messages.add_tool_card("shell_exec", {"command": "bad_command"})
        await pilot.pause()
        card_err.set_result("command not found", is_error=True)
        await pilot.pause()

        # Failure: additional line IS displayed!
        assert len(card_err.query("#tool-status")) == 1
        err_status = card_err.query_one("#tool-status")
        assert "Error" in str(err_status.content)

