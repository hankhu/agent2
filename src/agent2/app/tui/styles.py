"""Textual CSS styles for the Agent2 TUI."""

APP_CSS = """
Screen {
    background: $surface;
}

/* ── Status Bar ─────────────────────────────────────────────── */

StatusBar {
    dock: top;
    height: 1;
    background: $primary-background;
    color: $text;
    padding: 0 1;
    content-align-horizontal: left;
}

/* ── Message List ───────────────────────────────────────────── */

#messages {
    height: 1fr;
    overflow-y: auto;
    padding: 0 1;
}

UserMessage {
    margin: 1 0 0 0;
    padding: 0 1;
    background: $primary 15%;
    border-left: thick $primary;
    height: auto;
}

AssistantMessage {
    margin: 1 0 0 0;
    padding: 0 1;
    height: auto;
}

SystemMessage {
    margin: 1 0 0 0;
    padding: 0 1;
    color: $text-muted;
    height: auto;
}

/* ── Thinking Block ─────────────────────────────────────────── */

ThinkingBlock {
    margin: 0 0 0 2;
    height: auto;
}

ThinkingBlock > Contents {
    height: auto;
}

/* ── Tool Card ──────────────────────────────────────────────── */

ToolCard {
    margin: 0 0 0 2;
    padding: 0 1;
    border: round $warning;
    height: auto;
}

ToolCard .tool-result {
    height: auto;
    margin: 0;
}

ToolCard .tool-result > Contents {
    height: auto;
}

/* ── Diff View ──────────────────────────────────────────────── */

DiffView {
    margin: 0 0 0 2;
    padding: 1;
    border: round $accent;
    height: auto;
}

/* ── Input Area ─────────────────────────────────────────────── */

#input-area {
    dock: bottom;
    height: auto;
    max-height: 14;
}

#completion-list {
    display: none;
    height: auto;
    max-height: 8;
    margin: 0 1;
    border: round $primary;
    background: $surface;
}

#completion-list.visible {
    display: block;
}

#chat-input {
    height: auto;
    min-height: 3;
    max-height: 12;
    margin: 0 1;
    border: round $primary;
}

#chat-input:focus {
    border: round $accent;
}

#input-hint {
    height: 1;
    color: $text-muted;
    padding: 0 2;
    text-align: right;
}

/* ── Confirm Modal ──────────────────────────────────────────── */

ConfirmModal {
    align: center middle;
}

ConfirmModal #confirm-dialog {
    width: 76;
    height: auto;
    max-height: 80%;
    border: thick $warning;
    background: $surface;
    padding: 1 2;
}

ConfirmModal #confirm-dialog DiffView {
    margin: 1 0;
    max-height: 20;
    overflow-y: auto;
}

ConfirmModal #confirm-buttons {
    height: 3;
    align-horizontal: center;
    margin-top: 1;
}

ConfirmModal #confirm-buttons Button {
    margin: 0 1;
}

/* ── Model Select ───────────────────────────────────────────── */

ModelSelectScreen {
    align: center middle;
}

ModelSelectScreen #model-dialog {
    width: 84;
    height: auto;
    max-height: 80%;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

ModelSelectScreen DataTable {
    height: auto;
    max-height: 16;
    margin: 1 0;
}

ModelSelectScreen #model-input {
    margin: 1 0 0 0;
}
"""
