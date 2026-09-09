"""Textual CSS styles for the Agent2 TUI — modern flat minimalist design."""

APP_CSS = """
Screen {
    background: $surface;
    color: $text;
}

/* ── Top Navigation Bar ─────────────────────────────────────── */

TopTabBar {
    height: 1;
    width: 100%;
    layout: horizontal;
    background: $surface;
    padding: 0 1;
    margin: 0;
    border: none;
}

.top-tab {
    height: 1;
    width: auto;
    min-width: 9;
    padding: 0 1;
    margin: 0 1 0 0;
    color: $text-muted;
    background: transparent;
    text-align: center;
}

.top-tab:hover {
    color: $text;
    background: $panel 40%;
}

.top-tab.active {
    background: $primary;
    color: #ffffff;
    text-style: bold;
}

/* ── Welcome Banner ─────────────────────────────────────────── */

WelcomeBanner {
    height: auto;
    padding: 1 1 0 1;
    margin: 0;
    background: transparent;
}

/* ── Context Bar (Above Chat Input) ─────────────────────────── */

ContextBar {
    height: 1;
    background: transparent;
    color: $text-muted;
    padding: 0 1;
    margin: 0;
    border: none;
}

/* ── Status Bar / Footer (Bottom Row) ────────────────────────── */

StatusBar {
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
    margin: 0;
    border: none;
}

/* ── Message List ───────────────────────────────────────────── */

#messages {
    height: 1fr;
    overflow-y: auto;
    padding: 0;
    margin: 0;
}

UserMessage {
    margin: 0;
    padding: 0 1;
    background: $panel 35%;
    border: none;
    height: auto;
}

UserMessage.selected {
    background: $panel 65%;
    border: none;
}

AssistantMessage {
    margin: 0;
    padding: 0 1;
    background: transparent;
    border: none;
    height: auto;
}

AssistantMessage.selected {
    background: $panel 25%;
    border: none;
}

.message-actions {
    display: none;
    height: 1;
    min-height: 1;
    margin-top: 0;
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
    margin: 0;
    padding: 0 1;
    color: $text-muted;
    border: none;
    height: auto;
}

/* ── Thinking Block ─────────────────────────────────────────── */

ThinkingBlock {
    margin: 0;
    padding: 0 1;
    background: $panel 25%;
    border: none;
    height: auto;
}

ThinkingBlock > Contents {
    height: auto;
    padding: 0;
}

/* ── Tool Card ──────────────────────────────────────────────── */

ToolCard {
    margin: 0;
    padding: 0 1;
    background: $panel 30%;
    border: none;
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
    background: transparent;
}

ToolCard .tool-result > Contents {
    height: auto;
    padding: 0 1;
}

ToolCard .tool-result ToolTitle,
ToolCard .tool-result CollapsibleTitle {
    width: 100%;
    padding: 0;
    margin: 0;
    background: transparent;
}

ToolCard .tool-result ToolTitle:hover,
ToolCard .tool-result CollapsibleTitle:hover {
    background: $panel 50%;
}

ToolCard .tool-result ToolTitle:focus,
ToolCard .tool-result CollapsibleTitle:focus {
    background: $panel 60%;
}

/* ── Content & Diff Folding ─────────────────────────────────── */

.content-collapse {
    margin: 0;
    padding: 0 1;
    background: $panel 20%;
    border: none;
    height: auto;
}

.content-collapse > Contents {
    height: auto;
    padding: 0;
}

.content-collapse CollapsibleTitle {
    padding: 0;
    margin: 0;
}

.diff-collapse {
    margin: 0;
    padding: 0 1;
    background: $panel 20%;
    border: none;
    height: auto;
}

.diff-collapse > Contents {
    height: auto;
    padding: 0;
}

.diff-collapse CollapsibleTitle {
    padding: 0;
    margin: 0;
}

/* ── Diff View ──────────────────────────────────────────────── */

DiffView {
    margin: 0;
    padding: 0 1;
    background: $panel 35%;
    border: none;
    height: auto;
}

/* ── Input Area ─────────────────────────────────────────────── */

#input-area {
    height: auto;
    max-height: 14;
    background: $surface;
    border: none;
    padding: 0;
    margin: 0;
}

#completion-list {
    display: none;
    height: auto;
    max-height: 8;
    margin: 0;
    padding: 0;
    border: none;
    background: $panel;
}

#completion-list.visible {
    display: block;
}

#chat-input {
    height: auto;
    min-height: 2;
    max-height: 12;
    margin: 0;
    border: none;
    background: $surface-darken-1;
    padding: 0 1;
}

#chat-input:focus {
    border: none;
    background: $panel 60%;
}


#input-hint {
    height: 1;
    color: $text-muted;
    padding: 0 1;
    margin: 0;
    text-align: right;
}

/* ── Confirm Card (Inline Approval) ────────────────────────── */

ConfirmCard {
    margin: 0;
    padding: 0 1;
    background: $panel 40%;
    border: none;
    height: auto;
}

ConfirmCard DiffView {
    margin: 0;
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
    margin: 0;
    padding: 0 1;
    background: $panel 40%;
    border: none;
    height: auto;
}

/* ── Model Select ───────────────────────────────────────────── */

ModelSelectScreen {
    align: center middle;
    background: $background 60%;
    padding: 0;
    margin: 0;
}

ModelSelectScreen #model-dialog {
    width: 72;
    height: auto;
    max-height: 85%;
    border: none;
    background: $panel;
    padding: 0 1;
    margin: 0;
}

ModelSelectScreen Select {
    border: none;
    margin: 0;
    padding: 0;
}

ModelSelectScreen Select > SelectCurrent {
    border: none;
    background: $surface-darken-1;
    padding: 0 1;
}

ModelSelectScreen Select:focus > SelectCurrent {
    border: none;
    background: $panel-lighten-1 25%;
}

ModelSelectScreen Select > SelectOverlay {
    border: none;
    background: $panel-darken-1;
    padding: 0;
}

ModelSelectScreen #model-input {
    margin: 0;
    border: none;
    background: $surface-darken-1;
    padding: 0 1;
}

ModelSelectScreen #model-input:focus {
    border: none;
    background: $panel-lighten-1 25%;
}

/* ── Session Select ─────────────────────────────────────────── */

SessionSelectScreen {
    align: center middle;
    background: $background 60%;
    padding: 0;
    margin: 0;
}

SessionSelectScreen #session-dialog {
    width: 96;
    height: auto;
    max-height: 85%;
    border: none;
    background: $panel;
    padding: 0 1;
    margin: 0;
}

SessionSelectScreen DataTable {
    height: auto;
    max-height: 20;
    margin: 0;
    padding: 0;
    border: none;
}

SessionSelectScreen #rename-input {
    margin: 0;
    border: none;
    background: $surface-darken-1;
    padding: 0 1;
}

SessionSelectScreen #rename-input:focus {
    border: none;
    background: $panel-lighten-1 25%;
}

SessionSelectScreen #session-hint {
    margin: 0;
    padding: 0;
    color: $text-muted;
}
"""

