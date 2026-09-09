"""TUI widgets for agent2."""

from agent2.app.tui.widgets.confirm_modal import ConfirmCard, ConfirmModal
from agent2.app.tui.widgets.diff_view import DiffView
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import (
    AssistantMessage,
    MessageList,
    SystemMessage,
    ThinkingBlock,
    UserMessage,
)
from agent2.app.tui.widgets.nav_bar import TabItem, TopTabBar
from agent2.app.tui.widgets.shortcut_help import ShortcutHelp
from agent2.app.tui.widgets.status_bar import ContextBar, FooterBar, StatusBar
from agent2.app.tui.widgets.tool_card import ToolCard
from agent2.app.tui.widgets.welcome_banner import WelcomeBanner

__all__ = [
    "AssistantMessage",
    "ChatInput",
    "ConfirmCard",
    "ConfirmModal",
    "ContextBar",
    "DiffView",
    "FooterBar",
    "MessageList",
    "ShortcutHelp",
    "StatusBar",
    "SystemMessage",
    "TabItem",
    "ThinkingBlock",
    "ToolCard",
    "TopTabBar",
    "UserMessage",
    "WelcomeBanner",
]
