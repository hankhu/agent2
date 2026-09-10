"""Tests for modern TUI layout: TopTabBar, WelcomeBanner, ContextBar, FooterBar, and HelpScreen."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from agent2.agent.react import ReActAgent
from agent2.app.tui.app import Agent2App
from agent2.app.tui.screens.help import HelpScreen
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.nav_bar import TopTabBar
from agent2.app.tui.widgets.status_bar import ContextBar, FooterBar, StatusBar
from agent2.app.tui.widgets.welcome_banner import WelcomeBanner
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message


class DummyLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="dummy-model")

    async def chat(self, messages, tools=None):
        return LLMResponse(message=Message.assistant("Dummy reply"))


def test_welcome_banner_render() -> None:
    """Ensure WelcomeBanner renders Mascot and Tip correctly."""
    banner = WelcomeBanner(tip=("/plan", "Break down tasks"))
    rendered = banner.render()
    assert "Agent2" in rendered
    assert "/plan" in rendered
    assert "Break down tasks" in rendered
    assert "Verify outputs for correctness." in rendered


def test_top_tab_bar_cycling() -> None:
    """Test TopTabBar cycling between current, sessions, and skills."""
    tab_bar = TopTabBar()
    assert tab_bar.active_tab == "current"

    next_tab = tab_bar.cycle_tab(1)
    assert next_tab == "sessions"
    assert tab_bar.active_tab == "sessions"

    next_tab = tab_bar.cycle_tab(1)
    assert next_tab == "skills"
    assert tab_bar.active_tab == "skills"

    # Wraps back to current; Shift+Tab cycles in reverse.
    next_tab = tab_bar.cycle_tab(1)
    assert next_tab == "current"
    assert tab_bar.active_tab == "current"

    next_tab = tab_bar.cycle_tab(-1)
    assert next_tab == "skills"
    assert tab_bar.active_tab == "skills"


def test_context_bar_and_status_bar_rendering() -> None:
    """Test ContextBar and StatusBar render outputs."""
    cb = ContextBar()
    cb.cwd = "/test/repo"
    cb.input_tokens = 1200
    cb.output_tokens = 300
    cb_table = cb.render()
    assert cb_table is not None

    sb = StatusBar()
    sb.mode = "PLAN"
    sb_table = sb.render()
    assert sb_table is not None


@pytest.mark.asyncio
async def test_full_app_layout_widgets(tmp_path: Path) -> None:
    """Test that all modern widgets exist and mount in Agent2App."""
    from agent2.app.tui.session import SessionManager

    empty_sm = SessionManager(session_dir=tmp_path / "empty_sessions", log_dir=tmp_path / "empty_logs")
    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()), session_manager=empty_sm)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        top_bar = screen.query_one(TopTabBar)
        welcome = screen.query_one(WelcomeBanner)
        context_bar = screen.query_one(ContextBar)
        status_bar = screen.query_one(StatusBar)

        assert top_bar is not None
        assert welcome is not None
        assert context_bar is not None
        assert status_bar is not None

        # Verify initial active tab
        assert top_bar.active_tab == "current"

        # Tab switches the active top-level panel immediately and opens the sessions view
        from agent2.app.tui.screens.session_select import SessionSelectScreen

        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)
        assert app.screen.query_one(TopTabBar).active_tab == "sessions"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert top_bar.active_tab == "current"

        # '+' shortcut also opens the sessions view immediately
        await pilot.press("plus")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)
        assert app.screen.query_one(TopTabBar).active_tab == "sessions"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert top_bar.active_tab == "current"

        # '?' toggles the inline shortcut panel instead of a separate modal screen
        from agent2.app.tui.widgets.shortcut_help import ShortcutHelp

        shortcut = screen.query_one(ShortcutHelp)
        assert not shortcut.visible
        screen.query_one("#chat-input").focus()
        await pilot.press("question_mark")
        await pilot.pause()
        assert shortcut.visible
        await pilot.press("question_mark")
        await pilot.pause()
        assert not shortcut.visible


@pytest.mark.asyncio
async def test_help_screen_modal() -> None:
    """Test that HelpScreen can be pushed and dismissed."""
    class SimpleApp(App):
        def compose(self) -> ComposeResult:
            yield StatusBar()

    app = SimpleApp()
    async with app.run_test() as pilot:
        await app.push_screen(HelpScreen())
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        # Press escape to dismiss
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_top_tab_bar_width_and_visibility() -> None:
    """Ensure tabs in TopTabBar have proper width and are not collapsed."""
    class TabTestApp(App):
        def compose(self) -> ComposeResult:
            yield TopTabBar()

    app = TabTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        tab_bar = app.screen.query_one(TopTabBar)
        current = tab_bar.query_one("#tab-current")
        sessions = tab_bar.query_one("#tab-sessions")

        assert current.region.width > 0
        assert sessions.region.width > 0
        # Check they are positioned sequentially without overlapping
        assert current.region.x < sessions.region.x


@pytest.mark.asyncio
async def test_session_select_screen_modern() -> None:
    """Test modern SessionSelectScreen with search filtering and selection."""
    from agent2.app.tui.screens.session_select import SessionSelectScreen
    from textual.widgets import OptionList

    sessions = [
        {"id": "sess-alpha", "title": "Refactor AST Parser", "saved_at": 1000},
        {"id": "sess-beta", "title": "Write Unit Tests", "saved_at": 2000},
    ]

    class MockApp(App[str]):
        def compose(self) -> ComposeResult:
            yield StatusBar()

    app = MockApp()
    async with app.run_test(size=(100, 30)) as pilot:
        result: list[str] = []
        def on_done(val: str) -> None:
            result.append(val)

        await app.push_screen(SessionSelectScreen(sessions), callback=on_done)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, SessionSelectScreen)
        opt_list = screen.query_one("#session-list", OptionList)
        assert opt_list.option_count == 2

        # Filter by typing "AST"
        search = screen.query_one("#session-search")
        search.value = "AST"
        await pilot.pause()
        assert opt_list.option_count == 1

        # Press Enter to select
        await pilot.press("enter")
        await pilot.pause()
        assert result == ["sess-alpha"]


@pytest.mark.asyncio
async def test_completion_enter_accepts() -> None:
    """Ensure pressing Enter on slash command completion accepts completion like Tab."""
    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test() as pilot:
        screen = app.screen
        chat_input = screen.query_one("#chat-input")
        chat_input.focus()

        # Type '/' to trigger completion list
        await pilot.press("slash")
        await pilot.pause()
        assert chat_input.show_completion

        # Press Enter: should accept the highlighted completion instead of submitting empty/raw query
        await pilot.press("enter")
        await pilot.pause()

        # Completion accepted, input now contains a slash command with space
        assert not chat_input.show_completion
        assert chat_input.text.startswith("/")


@pytest.mark.asyncio
async def test_question_mark_toggles_shortcut_panel_and_clears_busy() -> None:
    """Ensure typing '?' immediately toggles the inline shortcut panel and leaves the UI idle."""
    from agent2.app.tui.widgets.shortcut_help import ShortcutHelp

    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test() as pilot:
        screen = app.screen
        chat_input = screen.query_one("#chat-input")
        shortcut = screen.query_one(ShortcutHelp)
        cb = screen.query_one(ContextBar)
        sb = screen.query_one(StatusBar)

        # '?' is intercepted on an empty input and shows the shortcut panel.
        chat_input.clear()
        await pilot.press("question_mark")
        await pilot.pause()

        assert shortcut.visible
        assert not isinstance(app.screen, HelpScreen)
        assert not cb.busy
        assert not sb.busy

        # Pressing '?' again hides the panel.
        await pilot.press("question_mark")
        await pilot.pause()
        assert not shortcut.visible
        assert not cb.busy
        assert not sb.busy

        # Send a normal query and verify that busy state is cleared when done
        chat_input.clear()
        chat_input.insert("Hello")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert not cb.busy
        assert not sb.busy
        assert cb.status_text == ""
        assert sb.status_text == ""


def test_resolve_provider_or_host() -> None:
    """Test resolve_provider_or_host with explicit providers, known URLs, unknown URLs, and ports."""
    from agent2.app.chat import resolve_provider_or_host

    # 1. Explicit valid provider
    assert resolve_provider_or_host("deepseek", "https://api.deepseek.com/v1") == "deepseek"
    assert resolve_provider_or_host("my-custom-provider", "https://llm.corp:8443/v1") == "my-custom-provider"
    assert resolve_provider_or_host("ollama", "http://localhost:11434/v1") == "ollama"

    # 2. Known provider in URL when provider is empty or generic
    assert resolve_provider_or_host(None, "https://api.deepseek.com/v1") == "deepseek"
    assert resolve_provider_or_host("", "https://api.openai.com/v1") == "openai"
    assert resolve_provider_or_host("default", "https://integrate.api.nvidia.com") == "nvidia"
    assert resolve_provider_or_host("config.models", "https://api.siliconflow.cn/v1") == "siliconflow"

    # 3. Unknown provider falls back to base_url host
    assert resolve_provider_or_host(None, "https://llm.internal.corp:8443/v1") == "llm.internal.corp:8443"
    assert resolve_provider_or_host("", "http://192.168.1.100:8000/v1") == "192.168.1.100:8000"
    assert resolve_provider_or_host("default", "http://localhost:11434/v1") == "localhost:11434"
    assert resolve_provider_or_host("custom", "https://gateway.ai.net/v1") == "gateway.ai.net"

    # 4. Empty / none
    assert resolve_provider_or_host(None, None) == ""
    assert resolve_provider_or_host("", "") == ""


def test_context_bar_provider_rendering() -> None:
    """Test ContextBar rendering includes provider tag when set."""
    cb = ContextBar()
    cb.model_name = "deepseek-chat"
    cb.provider = "deepseek"
    # render() returns rich Table
    table = cb.render()
    # Check that rows have the provider
    from rich.console import Console
    console = Console(record=True, width=120)
    console.print(table)
    out = console.export_text()
    assert "[deepseek] deepseek-chat" in out

    # Without provider
    cb.provider = ""
    table2 = cb.render()
    console2 = Console(record=True, width=120)
    console2.print(table2)
    out2 = console2.export_text()
    assert "deepseek-chat" in out2
    assert "[]" not in out2


@pytest.mark.asyncio
async def test_model_select_screen_renders_provider_and_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ModelSelectScreen lists models with provider or base_url host."""
    from textual.app import App, ComposeResult
    from textual.widgets import OptionList, Static
    from agent2.app.tui.screens.model_select import ModelSelectScreen

    fake_models = [
        {"name": "m1", "model": "deepseek-chat", "provider": "deepseek", "base_url": "https://api.deepseek.com/v1"},
        {"name": "m2", "model": "llama3.1", "provider": "", "base_url": "http://192.168.1.5:8000/v1"},
    ]
    monkeypatch.setattr(
        "agent2.app.tui.screens.model_select.get_available_models",
        lambda: fake_models,
    )

    class MiniApp(App):
        def compose(self) -> ComposeResult:
            yield Static("hi")

    app = MiniApp()
    async with app.run_test() as pilot:
        await app.push_screen(ModelSelectScreen())
        await pilot.pause()
        opt_list = app.screen.query_one("#model-list", OptionList)
        assert opt_list.option_count == 2
        line1 = str(opt_list.get_option_at_index(0).prompt)
        line2 = str(opt_list.get_option_at_index(1).prompt)
        assert "[deepseek] deepseek-chat" in line1
        assert "[192.168.1.5:8000] llama3.1" in line2


@pytest.mark.asyncio
async def test_sync_status_bar_syncs_provider() -> None:
    """Ensure _sync_status_bar sets provider on both StatusBar and ContextBar."""
    class LLMWithProvider(DummyLLM):
        def __init__(self) -> None:
            super().__init__()
            self.provider = "deepseek"
            self.base_url = "https://api.deepseek.com/v1"

    app = Agent2App(agent=ReActAgent(name="test", llm=LLMWithProvider()))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        cb = screen.query_one(ContextBar)
        sb = screen.query_one(StatusBar)
        assert cb.provider == "deepseek"
        assert sb.provider == "deepseek"


@pytest.mark.asyncio
async def test_chat_input_history_supports_slash_commands() -> None:
    """Ensure ChatInput records slash commands in history and allows navigating them."""
    from agent2.app.tui.app import TUIReActAgent
    from agent2.app.tui.widgets.input_area import ChatInput
    from unittest.mock import AsyncMock

    agent = TUIReActAgent(llm=DummyLLM())
    app = Agent2App(agent=agent)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        inp = app.screen.query_one(ChatInput)
        inp.focus()

        # Submit normal text
        inp.text = "hello world"
        await pilot.press("enter")
        await pilot.pause()

        # Submit slash commands
        inp.text = "/yolo"
        await pilot.press("enter")
        await pilot.pause()

        inp.text = "/yolo on"
        await pilot.press("enter")
        await pilot.pause()

        # History should contain all submitted items
        assert inp._history == ["hello world", "/yolo", "/yolo on"]

        # Navigate up
        await pilot.press("up")
        await pilot.pause()
        assert inp.text == "/yolo on"
        assert not inp.show_completion

        await pilot.press("up")
        await pilot.pause()
        assert inp.text == "/yolo"
        assert not inp.show_completion

        await pilot.press("up")
        await pilot.pause()
        assert inp.text == "hello world"

        # Navigate down
        await pilot.press("down")
        await pilot.pause()
        assert inp.text == "/yolo"

        await pilot.press("down")
        await pilot.pause()
        assert inp.text == "/yolo on"

        await pilot.press("down")
        await pilot.pause()
        assert inp.text == ""


@pytest.mark.asyncio
async def test_agent2_app_ctrl_z_suspend() -> None:
    """Ensure Ctrl+Z and Ctrl-Z trigger action_suspend_process."""
    from unittest.mock import MagicMock
    from agent2.app.tui.app import TUIReActAgent

    agent = TUIReActAgent(llm=DummyLLM())
    app = Agent2App(agent=agent)
    app.action_suspend_process = MagicMock()

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+z")
        assert app.action_suspend_process.call_count == 1
        await pilot.press("ctrl-z")
        assert app.action_suspend_process.call_count == 2


@pytest.mark.asyncio
async def test_shift_tab_from_sessions_highlights_current_tab() -> None:
    """Ensure switching from Sessions tab to Current tab via Shift+Tab lights up Current tab."""
    from agent2.app.tui.screens.session_select import SessionSelectScreen
    from agent2.app.tui.screens.skill_select import SkillSelectScreen
    from agent2.app.tui.screens.chat import ChatScreen

    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test(size=(100, 30)) as pilot:
        # Scenario 1: Tab into SessionSelectScreen, then Shift+Tab back to ChatScreen
        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)

        await pilot.press("shift+tab")
        await pilot.pause()
        assert isinstance(app.screen, ChatScreen)
        top_bar = app.screen.query_one(TopTabBar)
        assert top_bar.active_tab == "current"
        assert top_bar.query_one("#tab-current").has_class("active")
        assert not top_bar.query_one("#tab-sessions").has_class("active")

        # Scenario 2: Multi-hop panel cycling (Tab -> Tab -> Shift-Tab -> Shift-Tab)
        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)

        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, SkillSelectScreen)

        await pilot.press("shift+tab")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)

        # Focus sessions tab item explicitly in SessionSelectScreen
        app.screen.query_one("#tab-sessions").focus()
        await pilot.pause()

        # Shift-Tab back to Current tab
        await pilot.press("shift+tab")
        await pilot.pause()
        assert isinstance(app.screen, ChatScreen)
        top_bar = app.screen.query_one(TopTabBar)
        assert top_bar.active_tab == "current"
        assert top_bar.query_one("#tab-current").has_class("active")
        assert not top_bar.query_one("#tab-sessions").has_class("active")


@pytest.mark.asyncio
async def test_welcome_banner_anchored_at_top() -> None:
    """Ensure WelcomeBanner is pinned to the top of the start screen."""
    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test(size=(100, 30)) as pilot:
        banner = app.screen.query_one(WelcomeBanner)
        # Directly beneath the 1-line top-nav bar (y=1)
        assert banner.region.y == 1


@pytest.mark.asyncio
async def test_tab_cycles_candidates_in_completion() -> None:
    """Ensure Tab cycles candidate options when completion list is visible."""
    from textual.widgets import OptionList

    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test(size=(100, 30)) as pilot:
        chat_input = app.screen.query_one("#chat-input", ChatInput)
        chat_input.focus()

        # Type '/' to show completions
        await pilot.press("slash")
        await pilot.pause()
        assert chat_input.show_completion is True
        completion_list = app.screen.query_one("#completion-list", OptionList)
        assert completion_list.has_class("visible")
        assert completion_list.option_count > 1
        assert completion_list.highlighted == 0
        assert "❯" in str(completion_list.get_option_at_index(0).prompt)

        # Press Tab: cycles to the next candidate (index 1)
        await pilot.press("tab")
        await pilot.pause()
        assert chat_input.show_completion is True
        assert completion_list.highlighted == 1
        assert "❯" in str(completion_list.get_option_at_index(1).prompt)
        assert "❯" not in str(completion_list.get_option_at_index(0).prompt)

        # Press Shift+Tab: cycles back to candidate 0
        await pilot.press("shift+tab")
        await pilot.pause()
        assert completion_list.highlighted == 0
        assert "❯" in str(completion_list.get_option_at_index(0).prompt)

        # Press Enter: accepts candidate 0
        await pilot.press("enter")
        await pilot.pause()
        assert chat_input.show_completion is False
        assert not completion_list.has_class("visible")
        assert chat_input.text.startswith("/")
        assert chat_input.text.endswith(" ")


@pytest.mark.asyncio
async def test_tab_accepts_single_candidate_completion() -> None:
    """Ensure Tab accepts completion directly when there is only one candidate."""
    from textual.widgets import OptionList

    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test(size=(100, 30)) as pilot:
        chat_input = app.screen.query_one("#chat-input", ChatInput)
        chat_input.focus()

        # Type '/plan'
        for char in "/plan":
            await pilot.press(char)
        await pilot.pause()

        completion_list = app.screen.query_one("#completion-list", OptionList)
        assert completion_list.option_count == 1

        # Press Tab: immediately accepts single candidate
        await pilot.press("tab")
        await pilot.pause()
        assert chat_input.show_completion is False
        assert chat_input.text == "/plan "


@pytest.mark.asyncio
async def test_tab_switches_panel_when_not_completing() -> None:
    """Ensure Tab switches top panels when auto-completion is not active."""
    from agent2.app.tui.screens.session_select import SessionSelectScreen

    app = Agent2App(agent=ReActAgent(name="test", llm=DummyLLM()))
    async with app.run_test(size=(100, 30)) as pilot:
        chat_input = app.screen.query_one("#chat-input", ChatInput)
        chat_input.focus()

        # Normal text (no completion active)
        chat_input.text = "Hello world"
        chat_input.cursor_location = (0, 11)
        await pilot.pause()
        assert chat_input.show_completion is False

        # Press Tab: switches to Sessions panel
        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectScreen)
        assert app.screen.query_one(TopTabBar).active_tab == "sessions"


