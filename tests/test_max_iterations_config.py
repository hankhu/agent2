"""Tests for max iterations / max turns configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent2.agent.react import ReActAgent
from agent2.app.config import AppConfig
from agent2.app.tui.app import build_tui_agent
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message
from agent2.utils.config import settings


class DummyLLM(BaseLLM):
    """Dummy LLM for agent testing."""

    def __init__(self) -> None:
        super().__init__(model="dummy-model")

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        return LLMResponse(message=Message.assistant("Done"))


def test_default_max_iterations() -> None:
    """Verify default max iterations is 50 in settings and AppConfig."""
    assert settings.agent_max_iterations == 50

    cfg = AppConfig()
    assert cfg.max_iterations == 50
    assert cfg.max_turns == 50


def test_app_config_custom_max_iterations() -> None:
    """Verify AppConfig parses explicit max_iterations."""
    cfg = AppConfig.model_validate({"max_iterations": 25})
    assert cfg.max_iterations == 25
    assert cfg.max_turns == 25


def test_app_config_aliases() -> None:
    """Verify AppConfig accepts max_turns and max_rounds as aliases."""
    cfg_turns = AppConfig.model_validate({"max_turns": 35})
    assert cfg_turns.max_iterations == 35
    assert cfg_turns.max_turns == 35

    cfg_rounds = AppConfig.model_validate({"max_rounds": 42})
    assert cfg_rounds.max_iterations == 42
    assert cfg_rounds.max_turns == 42


def test_base_agent_default_max_iterations() -> None:
    """Verify BaseAgent/ReActAgent defaults to 50 when no args/config provided."""
    agent = ReActAgent(name="test_agent", llm=DummyLLM())
    assert agent.max_iterations == 50


def test_base_agent_reads_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify BaseAgent uses max_iterations from config.json when available."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"max_iterations": 18}), encoding="utf-8")

    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", config_file)

    agent = ReActAgent(name="test_agent", llm=DummyLLM())
    assert agent.max_iterations == 18


def test_base_agent_precedence_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify priority: code arg > env var > config.json > default."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"max_iterations": 20}), encoding="utf-8")
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", config_file)

    # 1. Config file alone gives 20
    agent1 = ReActAgent(name="test_agent", llm=DummyLLM())
    assert agent1.max_iterations == 20

    # 2. Env var overrides config file
    monkeypatch.setenv("AGENT2_AGENT_MAX_ITERATIONS", "75")
    from agent2.utils.config import Settings

    monkeypatch.setattr("agent2.agent.base.settings", Settings())

    agent2 = ReActAgent(name="test_agent", llm=DummyLLM())
    assert agent2.max_iterations == 75

    # 3. Explicit code argument overrides env var
    agent3 = ReActAgent(name="test_agent", llm=DummyLLM(), max_iterations=5)
    assert agent3.max_iterations == 5


def test_build_tui_agent_max_iterations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_tui_agent respects max_iterations parameter and config."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"max_iterations": 33}), encoding="utf-8")
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", config_file)
    monkeypatch.setattr("agent2.app.tui.app.create_llm", lambda *a, **kw: DummyLLM())

    # From config
    agent = build_tui_agent(no_tools=True)
    assert agent.max_iterations == 33

    # Explicit override
    agent_explicit = build_tui_agent(no_tools=True, max_iterations=12)
    assert agent_explicit.max_iterations == 12
