"""Textual CSS styles for the Agent2 TUI — modern flat minimalist design."""

APP_CSS = """
Screen {
    background: $surface;
    color: $text;
}

/* ── Status Bar ─────────────────────────────────────────────── */

StatusBar {
    dock: top;
    /* content row + the bottom border row: a 1-row bar with a border
       leaves zero content height and renders nothing. */
    height: 2;
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

UserMessage.selected {
    background: $panel 60%;
    border-left: double $primary;
}

AssistantMessage {
    margin: 1 0 0 0;
    padding: 1 1;
    background: transparent;
    height: auto;
}

AssistantMessage.selected {
    background: $panel 25%;
    border-left: double $secondary;
}

.message-actions {
    display: none;
    height: 1;
    min-height: 1;
    margin-top: 1;
    align-horizontal: right;
}

UserMessage.selected .message-actions {
    display: block;
}

AssistantMessage.selected .message-actions {
    display: block;
}

UserMessage:focus-within .message-actions {
    display: block;
}

AssistantMessage:focus-within .message-actions {
    display: block;
}

.message-actions Button {
    background: $panel 70%;
    border: none;
    height: 1;
    min-height: 1;
    min-width: 10;
    padding: 0 1;
    margin-left: 1;
    color: $text-muted;
}

.message-actions Button:hover {
    background: $primary 40%;
    color: $text;
}

.message-actions Button:focus {
    background: $primary 70%;
    color: $text;
    text-style: bold;
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

ToolCard #tool-status {
    margin: 0;
    padding: 0;
    height: auto;
}

ToolCard .tool-result {
    height: auto;
    margin: 0;
    padding: 0;
    border: none;
}

ToolCard .tool-result > Contents {
    height: auto;
    padding: 0;
}

ToolCard .tool-result CollapsibleTitle {
    padding: 0;
    margin: 0;
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

/* ── Confirm Card (Inline Approval) ────────────────────────── */

ConfirmCard {
    margin: 1 0 0 1;
    padding: 0 1;
    background: $panel 40%;
    border-left: solid $warning;
    height: auto;
}

ConfirmCard DiffView {
    margin: 1 0;
    max-height: 16;
    overflow-y: auto;
}

ConfirmCard #confirm-buttons {
    height: 1;
    min-height: 1;
    align-horizontal: left;
    margin: 0;
    padding: 0;
}

ConfirmCard #confirm-buttons Button {
    background: transparent;
    border: none;
    height: 1;
    min-height: 1;
    min-width: 8;
    padding: 0 1;
    margin: 0 1 0 0;
}

ConfirmCard #confirm-buttons Button:focus {
    background: $panel 80%;
    text-style: bold;
}

ConfirmCard #confirm-buttons Button:hover {
    background: $panel 60%;
}

ConfirmCard #confirm-status {
    margin: 0;
    height: 1;
}

ConfirmModal {
    margin: 1 0 0 1;
    padding: 0 1;
    background: $panel 40%;
    border-left: solid $warning;
    height: auto;
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

