"""Tests for /cfg command, backup_config, load_config fallback, and system editor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent2.app.config import (
    AppConfig,
    backup_config,
    get_system_editor,
    load_config,
    prepare_and_backup_config,
    validate_after_edit,
)
from agent2.app.tui.app import Agent2App, TUIReActAgent
from agent2.app.tui.screens.chat import SLASH_COMMANDS
from agent2.app.tui.widgets.input_area import ChatInput
from agent2.app.tui.widgets.message_list import MessageList
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message


class DummyLLM(BaseLLM):
    def __init__(self) -> None:
        super().__init__(model="dummy-model")

    async def chat(self, messages, tools=None):
        return LLMResponse(message=Message.assistant("Done"))


def test_slash_commands_include_cfg() -> None:
    cmds = {cmd for cmd, _ in SLASH_COMMANDS}
    assert "/cfg" in cmds
    assert "/config" in cmds


def test_backup_and_load_config_fallback(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "agent2"
    cfg_file = cfg_dir / "config.json"
    backup_file = cfg_dir / "config.json.backup"

    monkeypatch.setattr("agent2.app.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("agent2.app.config.CONFIG_BACKUP_FILE", backup_file)

    # 1. When config doesn't exist, backup returns False and load_config returns default
    assert not backup_config()
    default_cfg = load_config()
    assert default_cfg.default == "gpt-4o-mini"

    # 2. Write valid config and backup
    cfg_dir.mkdir(parents=True, exist_ok=True)
    valid_data = {
        "default": "deepseek-chat",
        "max_iterations": 35,
        "providers": {"deepseek": {"api_key": "sk-12345"}},
    }
    cfg_file.write_text(json.dumps(valid_data), encoding="utf-8")

    assert backup_config()
    assert backup_file.exists()
    assert json.loads(backup_file.read_text(encoding="utf-8"))["default"] == "deepseek-chat"

    loaded = load_config()
    assert loaded.default == "deepseek-chat"
    assert loaded.max_iterations == 35

    # 3. Corrupt config.json with invalid JSON syntax
    cfg_file.write_text("{ broken json syntax", encoding="utf-8")

    # load_config must catch the exception and use config.json.backup!
    fallback_loaded = load_config()
    assert fallback_loaded.default == "deepseek-chat"
    assert fallback_loaded.max_iterations == 35
    assert "deepseek" in fallback_loaded.providers

    # 4. If config.json is corrupted and backup is also corrupted, returns default AppConfig
    backup_file.write_text("also broken", encoding="utf-8")
    assert load_config().default == "gpt-4o-mini"


def test_get_system_editor(monkeypatch) -> None:
    # 1. Custom VISUAL
    monkeypatch.setenv("VISUAL", "code --wait")
    assert get_system_editor() == ["code", "--wait"]

    # 2. Custom EDITOR
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "nano -w")
    assert get_system_editor() == ["nano", "-w"]

    # 3. Fallback without env vars
    monkeypatch.delenv("EDITOR", raising=False)
    editor = get_system_editor()
    assert isinstance(editor, list)
    assert len(editor) >= 1


def test_prepare_and_backup_and_validate(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "agent2"
    cfg_file = cfg_dir / "config.json"
    backup_file = cfg_dir / "config.json.backup"

    monkeypatch.setattr("agent2.app.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("agent2.app.config.CONFIG_BACKUP_FILE", backup_file)

    # 1. Missing file -> prepare creates default template & backup
    backed_up, path_str = prepare_and_backup_config()
    assert cfg_file.exists()
    assert backup_file.exists()
    assert backed_up is True
    assert path_str == str(cfg_file)

    # 2. Valid edit -> validate_after_edit succeeds & updates backup
    cfg_file.write_text(json.dumps({"default": "test-model"}), encoding="utf-8")
    valid, msg = validate_after_edit()
    assert valid is True
    assert "successfully" in msg.lower()
    assert json.loads(backup_file.read_text(encoding="utf-8"))["default"] == "test-model"

    # 3. Invalid edit -> validate_after_edit fails & mentions fallback
    cfg_file.write_text("{ syntax error", encoding="utf-8")
    valid, msg = validate_after_edit()
    assert valid is False
    assert "error in config.json" in msg.lower()
    assert "fallback" in msg.lower()


@pytest.mark.asyncio
async def test_tui_handle_cfg_command(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "agent2"
    cfg_file = cfg_dir / "config.json"
    backup_file = cfg_dir / "config.json.backup"

    monkeypatch.setattr("agent2.app.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("agent2.app.config.CONFIG_BACKUP_FILE", backup_file)

    # Pre-populate config
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps({"default": "gpt-4o-mini"}), encoding="utf-8")

    app = Agent2App(agent=TUIReActAgent(llm=DummyLLM()))

    mock_run = MagicMock()
    with patch("subprocess.run", mock_run):
        async with app.run_test(size=(80, 24)) as pilot:
            screen = app.screen
            chat_input = screen.query_one("#chat-input", ChatInput)

            # Invoke /cfg
            chat_input.text = "/cfg"
            await pilot.press("enter")
            await pilot.pause()

            # Verify subprocess was called with editor and config path
            assert mock_run.call_count == 1
            args, _ = mock_run.call_args
            assert str(cfg_file) in args[0]

            # Verify backup file was created
            assert backup_file.exists()

            # Verify system messages in chat
            from agent2.app.tui.widgets.message_list import SystemMessage
            messages = screen.query_one("#messages", MessageList)
            sys_msgs = list(messages.query(SystemMessage))
            assert len(sys_msgs) >= 1
            all_text = " ".join(str(w.content) for w in sys_msgs)
            assert "Opening" in all_text or "config.json" in all_text
            assert "updated successfully" in all_text or "backed up" in all_text


@pytest.mark.asyncio
async def test_tui_handle_cfg_command_invalid_fallback(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "agent2"
    cfg_file = cfg_dir / "config.json"
    backup_file = cfg_dir / "config.json.backup"

    monkeypatch.setattr("agent2.app.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("agent2.app.config.CONFIG_BACKUP_FILE", backup_file)

    # Pre-populate valid config
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps({"default": "good-model"}), encoding="utf-8")

    app = Agent2App(agent=TUIReActAgent(llm=DummyLLM()))

    def corrupt_file_on_edit(*args, **kwargs):
        cfg_file.write_text("{ corrupt json", encoding="utf-8")

    with patch("subprocess.run", side_effect=corrupt_file_on_edit):
        async with app.run_test(size=(80, 24)) as pilot:
            chat_input = app.screen.query_one("#chat-input", ChatInput)
            chat_input.text = "/cfg"
            await pilot.press("enter")
            await pilot.pause()

            # Backup should exist and contain good-model
            assert backup_file.exists()
            assert json.loads(backup_file.read_text(encoding="utf-8"))["default"] == "good-model"

            # load_config() fallback is triggered and works
            active_cfg = load_config()
            assert active_cfg.default == "good-model"

            # Message list contains fallback notification
            from agent2.app.tui.widgets.message_list import MessageList, SystemMessage
            messages = app.screen.query_one("#messages", MessageList)
            all_text = " ".join(str(w.content) for w in messages.query(SystemMessage))
            assert "Fallback" in all_text or "backup" in all_text

