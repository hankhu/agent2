"""Tests for @file path autocompletion and context expansion."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from agent2.app.tui.file_completion import get_file_completions
from agent2.app.tui.screens.chat import _process_context


def test_get_file_completions_root(tmp_path: Path) -> None:
    # Create test directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.py").write_text("print('agent')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
    (tmp_path / ".git").mkdir()

    # Empty query should return root items
    completions = get_file_completions("", root_dir=tmp_path)
    tokens = [c[0] for c in completions]
    assert "@src/" in tokens
    assert "@README.md" in tokens
    assert "@pyproject.toml" in tokens
    assert "@.git/" not in tokens  # Ignored

    # Prefix match
    read_matches = get_file_completions("read", root_dir=tmp_path)
    assert len(read_matches) == 1
    assert read_matches[0][0] == "@README.md"

    # Directory prefix match
    src_matches = get_file_completions("src/", root_dir=tmp_path)
    assert len(src_matches) == 1
    assert src_matches[0][0] == "@src/agent.py"


def test_process_context_at_file_and_hash_file(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.py"
    test_file.write_text("x = 42\n", encoding="utf-8")

    # 1. Test @<path> syntax
    text_with_at = f"Please inspect @<{test_file}> and comment."
    processed = _process_context(text_with_at)
    assert f'<file path="{test_file}">' in processed
    assert "x = 42" in processed

    # 2. Test @path syntax (no angle brackets)
    text_with_raw_at = f"Look at @{test_file}"
    processed_raw = _process_context(text_with_raw_at)
    assert f'<file path="{test_file}">' in processed_raw

    # 3. Test #file syntax backwards compatibility
    text_with_hash = f"Check #file {test_file}"
    processed_hash = _process_context(text_with_hash)
    assert f'<file path="{test_file}">' in processed_hash

    # 4. Ordinary email or non-existing mention should remain unchanged
    email_text = "Contact support@example.com or @nonexistent_user"
    assert _process_context(email_text) == email_text
