"""Textual CSS styles for the Agent2 TUI — modern flat minimalist design."""

APP_CSS = """
Screen {
    background: $surface;
    color: $text;
}

/* ── Status Bar ─────────────────────────────────────────────── */

StatusBar {
    dock: top;
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
    content-align-horizontal: left;
    border-bottom: solid $panel-lighten-1 25%;
}

/* ── Message List ───────────────────────────────────────────── */

#messages {
    height: 1fr;
    overflow-y: auto;
    padding: 1 1;
}

UserMessage {
    margin: 1 0 0 0;
    padding: 1 1;
    background: $panel 35%;
    border-left: solid $primary;
    height: auto;
}

AssistantMessage {
    margin: 1 0 0 0;
    padding: 1 1;
    background: transparent;
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
    margin: 1 0 0 1;
    padding: 0 1;
    background: $panel 25%;
    border-left: solid $secondary 60%;
    height: auto;
}

ThinkingBlock > Contents {
    height: auto;
    padding: 0;
}

/* ── Tool Card ──────────────────────────────────────────────── */

ToolCard {
    margin: 1 0 0 1;
    padding: 0 1;
    background: $panel 30%;
    border-left: solid $warning;
    height: auto;
}

ToolCard .tool-result {
    height: auto;
    margin: 0;
    border: none;
}

ToolCard .tool-result > Contents {
    height: auto;
    padding: 0;
}

/* ── Diff View ──────────────────────────────────────────────── */

DiffView {
    margin: 1 0 0 1;
    padding: 0 1;
    background: $panel 35%;
    border-left: solid $accent;
    height: auto;
}

/* ── Input Area ─────────────────────────────────────────────── */

#input-area {
    dock: bottom;
    height: auto;
    max-height: 14;
    background: $surface;
    border-top: solid $panel-lighten-1 35%;
    padding: 0 0 1 0;
}

#completion-list {
    display: none;
    height: auto;
    max-height: 8;
    margin: 0 1 1 1;
    border: solid $primary 50%;
    background: $panel;
}

#completion-list.visible {
    display: block;
}

#chat-input {
    height: auto;
    min-height: 3;
    max-height: 12;
    margin: 0 1;
    border: solid $panel-lighten-1 50%;
    background: $surface-darken-1;
}

#chat-input:focus {
    border: solid $primary;
}


#input-hint {
    height: 1;
    color: $text-muted;
    padding: 0 2;
    text-align: right;
}

/* ── Confirm Modal ──────────────────────────────────────────── */

ConfirmModal {
    align: center bottom;
    background: $background 60%;
}

ConfirmModal #confirm-dialog {
    width: 100%;
    height: auto;
    max-height: 80%;
    border-top: solid $warning;
    background: $panel;
    padding: 1 2;
    margin-bottom: 0;
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
    border: none;
}

/* ── Model Select ───────────────────────────────────────────── */

ModelSelectScreen {
    align: center middle;
    background: $background 60%;
}

ModelSelectScreen #model-dialog {
    width: 86;
    height: auto;
    max-height: 85%;
    border: solid $primary;
    background: $panel;
    padding: 1 2;
}

ModelSelectScreen DataTable {
    height: auto;
    max-height: 16;
    margin: 1 0;
    border: none;
}

ModelSelectScreen #model-input {
    margin: 1 0 0 0;
    border: solid $primary 50%;
}

ModelSelectScreen #model-input:focus {
    border: solid $primary;
}

/* ── Session Select ─────────────────────────────────────────── */

SessionSelectScreen {
    align: center middle;
    background: $background 60%;
}

SessionSelectScreen #session-dialog {
    width: 96;
    height: auto;
    max-height: 85%;
    border: solid $primary;
    background: $panel;
    padding: 1 2;
}

SessionSelectScreen DataTable {
    height: auto;
    max-height: 20;
    margin: 1 0;
    border: none;
}

SessionSelectScreen #rename-input {
    margin: 1 0 0 0;
    border: solid $primary 50%;
}

SessionSelectScreen #rename-input:focus {
    border: solid $primary;
}

SessionSelectScreen #session-hint {
    margin: 1 0 0 0;
    color: $text-muted;
}
"""

