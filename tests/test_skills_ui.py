"""Tests for SkillSelectScreen and TUI skill integration."""

from __future__ import annotations

from pathlib import Path
import pytest
from textual.app import App, ComposeResult
from textual.widgets import OptionList

from agent2.app.tui.screens.skill_select import SkillSearchInput, SkillSelectScreen
from agent2.context import SkillInfo


@pytest.mark.asyncio
async def test_skill_select_screen_mount_and_filter(tmp_path: Path):
    skills = [
        SkillInfo(
            name="code-review",
            description="Performs automated code reviews",
            path=tmp_path / "code-review",
            content="Instructions for code review",
            source="~/.agent2/skills",
        ),
        SkillInfo(
            name="deploy",
            description="Deploys the application",
            path=tmp_path / "deploy",
            content="Instructions for deployment",
            source="~/.claude/skills",
        ),
    ]

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield OptionList()

    app = TestApp()
    async with app.run_test() as pilot:
        screen = SkillSelectScreen(skills=skills)
        await app.push_screen(screen)
        await pilot.pause()

        opt_list = screen.query_one("#skill-list", OptionList)
        assert opt_list.option_count == 2

        # Search filter
        search = screen.query_one("#skill-search", SkillSearchInput)
        search.value = "deploy"
        await pilot.pause()
        assert opt_list.option_count == 1

        # Clear filter
        search.value = ""
        await pilot.pause()
        assert opt_list.option_count == 2


@pytest.mark.asyncio
async def test_skill_select_screen_selection(tmp_path: Path):
    skills = [
        SkillInfo(
            name="git-expert",
            description="Git wizardry",
            path=tmp_path / "git-expert",
            content="Git instructions",
            source=".agent2/skills",
        ),
    ]

    selected_result: list[str] = []

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield OptionList()

    app = TestApp()
    async with app.run_test() as pilot:
        screen = SkillSelectScreen(skills=skills)
        await app.push_screen(screen, callback=lambda val: selected_result.append(val))
        await pilot.pause()

        # Press enter on the highlighted option
        await pilot.press("enter")
        await pilot.pause()

        assert selected_result == ["git-expert"]


def test_get_all_commands_includes_skills():
    from agent2.app.tui.screens.chat import get_all_commands
    from agent2.context import Context

    ctx = Context(
        skills=[
            SkillInfo(
                name="custom-skill",
                description="My custom skill description",
                path=Path("/tmp"),
                content="...",
            )
        ]
    )
    cmds = get_all_commands(ctx)
    cmd_dict = dict(cmds)
    assert "/custom-skill" in cmd_dict
    assert "My custom skill description" in cmd_dict["/custom-skill"]
    assert "/plan" in cmd_dict
    assert "/skills" in cmd_dict


@pytest.mark.asyncio
async def test_chat_input_auto_complete_includes_skills(tmp_path: Path):
    from agent2.agent.react import ReActAgent
    from agent2.app.tui.app import Agent2App
    from agent2.app.tui.session import SessionManager
    from agent2.context import Context
    from agent2.llm.base import BaseLLM
    from agent2.llm.message import LLMResponse, Message

    class DummyLLM(BaseLLM):
        def __init__(self) -> None:
            super().__init__(model="dummy-model")

        async def chat(self, messages, tools=None):
            return LLMResponse(message=Message.assistant("Dummy reply"))

    ctx = Context(
        skills=[
            SkillInfo(
                name="test-automation",
                description="Automated tests",
                path=tmp_path / "test-automation",
                content="Instructions",
            )
        ]
    )
    empty_sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    app = Agent2App(
        agent=ReActAgent(name="test", llm=DummyLLM()),
        session_manager=empty_sm,
        context=ctx,
    )
    async with app.run_test() as pilot:
        screen = app.screen
        chat_input = screen.query_one("#chat-input")
        chat_input.focus()

        # Type '/test' to trigger completion
        chat_input.insert("/test")
        await pilot.pause()

        assert chat_input.show_completion
        completion = screen.query_one("#completion-list", OptionList)
        assert completion.option_count >= 1
        options_text = [str(completion.get_option_at_index(i).prompt) for i in range(completion.option_count)]
        assert any("/test-automation" in opt for opt in options_text)

        # Press Enter to accept completion
        await pilot.press("enter")
        await pilot.pause()

        assert not chat_input.show_completion
        assert chat_input.text.startswith("/test-automation")

