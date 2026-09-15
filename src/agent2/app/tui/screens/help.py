"""Help screen modal — keyboard shortcuts, commands, and modes."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static


HELP_MARKDOWN = """
### 🚀 Modes
- **/agent** `[prompt]`: Default full autonomous agent mode with tool execution
- **/plan** `[goal]`: Intent analysis & DAG task breakdown with sub-agents
- **/ask** `[query]`: Read-only mode (file write & shell execution disabled)

### ⌨️ Keyboard Shortcuts
- **Enter**: Send message
- **Shift+Enter**: Insert newline in input
- **Tab / Shift+Tab**: Switch to the next / previous top-level panel
- **?**: Toggle the inline shortcut panel above the chat input
- **+**: Open the Sessions panel immediately
- **Ctrl+C**: Interrupt agent generation or tool execution
- **Ctrl+O**: Toggle tool execution results expand/collapse
- **Ctrl+D**: Save session and exit
- **Ctrl+Z**: Suspend to background
- **Esc**: Close popup dialog / cancel message selection

### 🛠️ Slash Commands
- **/model** `[name]`: Switch LLM model
- **/sessions**: List, resume, rename, or delete saved sessions
- **/compact** `[keep]`: Compact conversation context to free window capacity
- **/clear**: Clear current screen display
- **/retry**: Retry last user query / regenerate response
- **/continue**: Continue execution if paused
- **/rewind**: Rewind to previous conversation round
- **/fork** `[title]`: Fork current session into a new branch
- **/export** `[path]`: Export conversation history to file
- **/cfg**: Open configuration (~/.config/agent2/config.json) in system editor
- **/yolo** `[on|off|show]`: YOLO / Autopilot mode (auto-approve & autonomous decisions)
- **/allow-all** `[on|off|show]`: Auto-approve all tool operations

### 📁 Context Injection
- **@`<file path>`**: File/directory autocomplete and inline context injection
- **#file `<path>`**: Inject specified file content into context
- **#dir `<path>`**: Inject directory listing into context
"""


class HelpScreen(ModalScreen[None]):
    """Modal dialog displaying comprehensive help and shortcuts."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }

    #help-dialog {
        width: 78;
        height: auto;
        max-height: 85%;
        background: #161b22;
        border: none;
        padding: 1 2;
    }

    #help-header {
        height: 1;
        margin-bottom: 1;
        color: #58a6ff;
        text-style: bold;
    }

    #help-content {
        height: auto;
        max-height: 22;
        overflow-y: auto;
        margin-bottom: 1;
    }

    #help-close-btn {
        width: 100%;
        height: 1;
        min-height: 1;
        background: #21262d;
        color: #c9d1d9;
        border: none;
    }

    #help-close-btn:hover {
        background: #1f6feb;
        color: #ffffff;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", priority=True),
        Binding("enter", "dismiss_help", "Close", priority=True),
    ]

    def compose(self):  # type: ignore[override]
        with Vertical(id="help-dialog"):
            yield Static("📖 Agent2 Help & Keybindings", id="help-header")
            yield Markdown(HELP_MARKDOWN, id="help-content")
            yield Button("Close (Esc)", id="help-close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close-btn":
            self.dismiss(None)

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
