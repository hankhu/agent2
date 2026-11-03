"""Tests for built-in /setup skill packaged in agent2-tui."""

from __future__ import annotations

from pathlib import Path
import pytest

from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.screens.chat import SLASH_COMMANDS
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import MessageList, UserMessage
from agent2.context import discover_skills
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message


class DummyLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="dummy-model")
        self.received_prompts: list[str] = []

    async def chat(self, messages, tools=None):
        for m in messages:
            if m.content:
                self.received_prompts.append(m.content)
        return LLMResponse(message=Message.assistant("Setup assistance ready."))


def test_setup_skill_packaged_and_discoverable() -> None:
    skills = discover_skills()
    setup_skills = [s for s in skills if s.name.lower() == "setup"]
    assert len(setup_skills) == 1, f"Expected 1 setup skill, found: {setup_skills}"

    skill = setup_skills[0]
    assert skill.source == "builtin/tui"
    assert "agent2-tui" in skill.description
    assert "config.json" in skill.content
    assert (skill.path / "SKILL.md").is_file()


def test_slash_commands_include_setup() -> None:
    cmds = {cmd for cmd, _ in SLASH_COMMANDS}
    assert "/setup" in cmds


@pytest.mark.asyncio
async def test_tui_handle_setup_command() -> None:
    dummy_llm = DummyLLM()
    agent = TUIReActAgent(llm=dummy_llm)
    app = Agent2App(agent=agent)

    async with app.run_test(size=(80, 24)) as pilot:
        screen = app.screen
        chat_input = screen.query_one("#chat-input", ChatInput)

        # Send /setup
        chat_input.text = "/setup"
        await pilot.press("enter")
        await pilot.pause()

        # Verify /setup user message is rendered in MessageList
        messages = screen.query_one("#messages", MessageList)
        user_msgs = list(messages.query(UserMessage))
        assert len(user_msgs) >= 1
        assert any("/setup" in u._text for u in user_msgs)

        # Verify LLM received prompt containing [Skill: setup]
        assert any("[Skill: setup]" in p for p in dummy_llm.received_prompts)
