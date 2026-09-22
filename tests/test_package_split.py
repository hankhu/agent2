"""Tests for agent2 and agent2-tui packaging and decoupling."""

import pytest
from agent2.app.common import YOLO_INSTRUCTION, process_context, _process_context


def test_common_yolo_instruction() -> None:
    assert "[YOLO / Autopilot Mode Active]" in YOLO_INSTRUCTION


def test_common_process_context(tmp_path) -> None:
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello world", encoding="utf-8")

    expanded = process_context(f"read #file {test_file}")
    assert f'<file path="{test_file}">' in expanded
    assert "hello world" in expanded
    assert _process_context == process_context


def test_cli_dispatch_fallback(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from agent2.app import cli

    # Simulate tui not installed
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "agent2.app.tui":
            raise ImportError("No module named 'agent2.app.tui'")
        return real_import(name, *args, **kwargs)

    called = []
    monkeypatch.setattr(builtins, "__import__", mock_import)
    monkeypatch.setattr("agent2.app.chat.main", lambda argv=None: called.append("chat"))

    cli.main(["--help"])
    assert called == ["chat"]


def test_cli_dispatch_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent2.app import cli

    called = []
    monkeypatch.setattr("agent2.app.tui.main", lambda argv=None: called.append("tui"))

    cli.main([])
    assert called == ["tui"]


def test_version_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata

    # Test fallback to agent2-core
    def fake_version(pkg: str) -> str:
        if pkg == "agent2":
            raise importlib.metadata.PackageNotFoundError
        if pkg == "agent2-core":
            return "0.1.3.24"
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    import importlib
    import agent2
    importlib.reload(agent2)
    assert agent2.__version__ == "0.1.3.24"
