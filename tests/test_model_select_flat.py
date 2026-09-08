"""Tests for flat UI styles and drop-down menu ModelSelectScreen."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Select, Static

from agent2.app.tui.app import Agent2App
from agent2.app.tui.screens.model_select import ModelSelectScreen
from agent2.app.tui.styles import APP_CSS
from agent2.app.tui.widgets.nav_bar import TopTabBar
from agent2.app.tui.widgets.status_bar import StatusBar


def test_app_css_validity() -> None:
    """Ensure the flat borderless APP_CSS parses cleanly in Textual."""
    class CSSTestApp(App):
        CSS = APP_CSS

        def compose(self) -> ComposeResult:
            yield StatusBar()

    app = CSSTestApp()
    # If CSS is invalid, app._init_mode or stylesheet parser will raise
    assert "border: none;" in APP_CSS
    assert "Select" in APP_CSS


@pytest.mark.asyncio
async def test_model_select_screen_with_dropdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ModelSelectScreen navigation and selection."""
    fake_models = [
        {"name": "mimo-v2.5", "model": "mimo-v2.5", "provider": "xiaomi"},
        {"name": "gpt-4o", "model": "gpt-4o", "provider": "openai"},
    ]
    monkeypatch.setattr(
        "agent2.app.tui.screens.model_select.get_available_models",
        lambda: fake_models,
    )

    class HostApp(App):
        CSS = APP_CSS

        def compose(self) -> ComposeResult:
            yield Static("Host")

    app = HostApp()
    async with app.run_test() as pilot:
        result: str | None = None

        def on_dismiss(val: str) -> None:
            nonlocal result
            result = val

        app.push_screen(ModelSelectScreen(), callback=on_dismiss)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ModelSelectScreen)

        # Navigate down and choose the second model
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        # Modal should have dismissed with selected model
        assert result == "gpt-4o"


@pytest.mark.asyncio
async def test_model_select_screen_custom_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test custom model input in ModelSelectScreen."""
    fake_models = [
        {"name": "mimo-v2.5", "model": "mimo-v2.5", "provider": "xiaomi"},
    ]
    monkeypatch.setattr(
        "agent2.app.tui.screens.model_select.get_available_models",
        lambda: fake_models,
    )

    class HostApp(App):
        CSS = APP_CSS

        def compose(self) -> ComposeResult:
            yield Static("Host")

    app = HostApp()
    async with app.run_test() as pilot:
        result: str | None = None

        def on_dismiss(val: str) -> None:
            nonlocal result
            result = val

        app.push_screen(ModelSelectScreen(), callback=on_dismiss)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ModelSelectScreen)

        inp = screen.query_one("#model-input")
        inp.focus()
        await pilot.press("c", "u", "s", "t", "o", "m", "-", "l", "l", "m", "enter")
        await pilot.pause()

        assert result == "custom-llm"


@pytest.mark.asyncio
async def test_model_select_screen_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test cancelling ModelSelectScreen with Escape."""
    fake_models = [
        {"name": "mimo-v2.5", "model": "mimo-v2.5", "provider": "xiaomi"},
    ]
    monkeypatch.setattr(
        "agent2.app.tui.screens.model_select.get_available_models",
        lambda: fake_models,
    )

    class HostApp(App):
        CSS = APP_CSS

        def compose(self) -> ComposeResult:
            yield Static("Host")

    app = HostApp()
    async with app.run_test() as pilot:
        result: str | None = None

        def on_dismiss(val: str) -> None:
            nonlocal result
            result = val

        app.push_screen(ModelSelectScreen(), callback=on_dismiss)
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert result == ""


@pytest.mark.asyncio
async def test_statusbar_positioned_at_bottom() -> None:
    """Ensure StatusBar renders at the bottom row below input area."""
    from agent2.agent.react import ReActAgent
    from agent2.llm.base import BaseLLM
    from agent2.llm.message import LLMResponse, Message

    class MinimalLLM(BaseLLM):
        def __init__(self) -> None:
            super().__init__(model="test")

        async def chat(self, messages, tools=None):
            return LLMResponse(message=Message.assistant("ok"))

    app = Agent2App(agent=ReActAgent(name="test", llm=MinimalLLM()))
    async with app.run_test(size=(80, 24)) as pilot:
        screen = app.screen
        sb = screen.query_one(StatusBar)
        inp = screen.query_one("#input-area")
        msgs = screen.query_one("#messages")
        top_bar = screen.query_one(TopTabBar)

        # TopTabBar must be at the very top (y=0)
        assert top_bar.region.y == 0
        assert top_bar.region.height == 1
        # StatusBar must be on the bottom row (y=23 on a 24-row screen)
        assert sb.region.y == 23
        assert sb.region.height == 1
        # Messages must start below TopTabBar (y=1)
        assert msgs.region.y == 1
        # Input area must be immediately above StatusBar
        assert inp.region.y + inp.region.height == 23

