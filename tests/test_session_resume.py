import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent2.agent.base import BaseAgent
from agent2.agent.react import ReActAgent
from agent2.app.tui import _print_exit_info, main, parse_args
from agent2.app.tui.app import restore_agent
from agent2.app.tui.session import SessionManager
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Role


class DummyLLM(BaseLLM):
    def __init__(self, model: str = "dummy-model") -> None:
        super().__init__(model=model)

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        return LLMResponse(message=Message.assistant("Dummy response"))


def test_session_manager_get_latest_and_find(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path)
    assert sm.get_latest_session() is None
    assert sm.find_session("any") is None
    assert sm.find_session("") is None

    # Save session 1
    agent_data_1 = {
        "name": "assistant",
        "agent_type": "react",
        "system_prompt": "sys prompt",
        "messages": [
            {"role": "user", "content": "Fix bug in parser"},
            {"role": "assistant", "content": "Bug fixed"},
        ],
    }
    sm.save("sess001", agent_data_1, title="Parser Bugfix")

    # Save session 2
    agent_data_2 = {
        "name": "assistant",
        "agent_type": "react",
        "system_prompt": "sys prompt",
        "messages": [
            {"role": "user", "content": "Add unit tests"},
            {"role": "assistant", "content": "Tests added"},
        ],
    }
    sm.save("sess002", agent_data_2, title="Unit Tests")

    # get_latest_session
    latest = sm.get_latest_session()
    assert latest is not None
    assert latest["id"] == "sess002"

    # find_session exact ID
    match = sm.find_session("sess001")
    assert match is not None
    assert match["id"] == "sess001"

    # find_session prefix ID
    match = sm.find_session("sess00")
    assert match is not None
    assert match["id"] == "sess002"  # newest first

    # find_session exact title (case-insensitive)
    match = sm.find_session("parser bugfix")
    assert match is not None
    assert match["id"] == "sess001"

    # find_session substring title (case-insensitive)
    match = sm.find_session("bugfix")
    assert match is not None
    assert match["id"] == "sess001"

    match = sm.find_session("test")
    assert match is not None
    assert match["id"] == "sess002"

    # find_session not found
    assert sm.find_session("nonexistent") is None


def test_parse_args_resume_and_continue() -> None:
    args = parse_args(["--resume", "sess123"])
    assert args.resume == "sess123"
    assert not args.continue_session

    args = parse_args(["--continue"])
    assert args.continue_session
    assert args.resume is None

    args = parse_args(["-c"])
    assert args.continue_session
    assert args.resume is None

    # Mutually exclusive
    with pytest.raises(SystemExit):
        parse_args(["--resume", "sess123", "--continue"])


def test_parse_args_version(capsys: pytest.CaptureFixture[str]) -> None:
    from agent2 import __version__

    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out

    with pytest.raises(SystemExit) as exc_info:
        parse_args(["-v"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_restore_agent(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path)
    llm = DummyLLM("test-model")
    agent = ReActAgent(name="test_agent", llm=llm)

    agent_data = {
        "name": "test_agent",
        "agent_type": "react",
        "system_prompt": "Custom system prompt",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "World"},
        ],
    }
    sm.save("sess_test", agent_data, title="Greeting Session")

    title = restore_agent(agent, sm, "sess_test")
    assert title == "Greeting Session"
    assert agent.system_prompt == "Custom system prompt"
    assert len(agent.messages) == 2
    assert agent.messages[0].content == "Hello"
    assert agent.messages[1].content == "World"


def test_print_exit_info(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_file = tmp_path / "test.log"
    _print_exit_info("abcd1234", log_file)
    captured = capsys.readouterr().out
    assert "Session ID:" not in captured
    assert "Resume with: agent2 --resume abcd1234" in captured
    assert f"Log file:    {log_file}" in captured
    assert log_file.exists()


def test_main_continue_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: SessionManager(session_dir=tmp_path))
    with pytest.raises(SystemExit) as exc_info:
        main(["--continue"])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "No saved sessions found to continue." in err


def test_main_resume_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: SessionManager(session_dir=tmp_path))
    with pytest.raises(SystemExit) as exc_info:
        main(["--resume", "missing_session"])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Session 'missing_session' not found." in err


def test_main_single_turn_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: sm)

    dummy_llm = DummyLLM()
    monkeypatch.setattr("agent2.app.tui.build_tui_agent", lambda **kwargs: ReActAgent(name="assistant", llm=dummy_llm))

    # Run single-turn command
    main(["-p", "What is 2+2?"])
    captured = capsys.readouterr().out
    assert captured == "Dummy response\n"

    latest = sm.get_latest_session()
    assert latest is not None
    session_id = latest["id"]
    log_path = sm.get_log_path(session_id)
    assert log_path.exists()
    assert "[USER] What is 2+2?" in log_path.read_text(encoding="utf-8")

    # Resume the session with --continue and another -p
    main(["--continue", "-p", "What is 3+3?"])
    captured2 = capsys.readouterr().out
    assert captured2 == "Dummy response\n"
    assert log_path.exists()

    # Check conversation history in saved session
    data = sm.load(session_id)
    messages = data["agent"]["messages"]
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    assert user_msgs == ["What is 2+2?", "What is 3+3?"]


def test_main_resume_by_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: sm)

    dummy_llm = DummyLLM()
    monkeypatch.setattr("agent2.app.tui.build_tui_agent", lambda **kwargs: ReActAgent(name="assistant", llm=dummy_llm))

    agent_data = {
        "name": "assistant",
        "agent_type": "react",
        "system_prompt": "sys prompt",
        "messages": [
            {"role": "user", "content": "Review code"},
            {"role": "assistant", "content": "Code looks good"},
        ],
    }
    sm.save("review123", agent_data, title="Code Review Task")

    main(["--resume", "Code Review", "-p", "Check performance"])
    captured = capsys.readouterr().out
    assert captured == "Dummy response\n"
    assert (tmp_path / "logs" / "review123.log").exists()

    data = sm.load("review123")
    user_msgs = [m["content"] for m in data["agent"]["messages"] if m["role"] == "user"]
    assert user_msgs == ["Review code", "Check performance"]


def test_main_interactive_exit_with_messages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: sm)

    dummy_llm = DummyLLM()
    monkeypatch.setattr("agent2.app.tui.build_tui_agent", lambda **kwargs: ReActAgent(name="assistant", llm=dummy_llm))

    def fake_run(self):
        # Simulate user having sent a message during TUI run
        self.agent._messages.append(Message.user("Hello from TUI"))
        self.agent._messages.append(Message.assistant("Hello back"))

    monkeypatch.setattr("agent2.app.tui.Agent2App.run", fake_run)

    main([])
    captured = capsys.readouterr().out
    assert "Session ID:" not in captured
    assert "Resume with: agent2 --resume" in captured
    assert "Log file:" in captured


def test_main_interactive_exit_empty_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sm = SessionManager(session_dir=tmp_path)
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: sm)

    dummy_llm = DummyLLM()
    monkeypatch.setattr("agent2.app.tui.build_tui_agent", lambda **kwargs: ReActAgent(name="assistant", llm=dummy_llm))

    def fake_run_empty(self):
        # User quits immediately without sending messages
        pass

    monkeypatch.setattr("agent2.app.tui.Agent2App.run", fake_run_empty)

    main([])
    captured = capsys.readouterr().out
    assert "Session ID:" not in captured
    assert "Resume with:" not in captured
    assert "Log file:" not in captured


def test_session_logging_and_cleanup(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    log_path = sm.get_log_path("sess100")
    sm.log_event("sess100", "USER", "How is the weather?")
    sm.log_event("sess100", "ACTION", "get_weather(city='Beijing')")
    sm.log_event("sess100", "OBSERVATION", "Sunny 25C")

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "[USER] How is the weather?" in content
    assert "[ACTION] get_weather(city='Beijing')" in content
    assert "[OBSERVATION] Sunny 25C" in content

    # Test delete cleans up log
    sm.save("sess100", {"messages": []}, title="Weather")
    sm.delete("sess100")
    assert not (tmp_path / "sessions" / "sess100.json").exists()
    assert not log_path.exists()


def test_session_export_formats(tmp_path: Path) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent_data = {
        "name": "assistant",
        "agent_type": "react",
        "system_prompt": "You are a helpful assistant.",
        "messages": [
            {"role": "user", "content": "Write a python function"},
            {
                "role": "assistant",
                "content": "Here is the code:",
                "tool_calls": [{"id": "call1", "name": "file_write", "arguments": {"path": "main.py"}}],
            },
            {
                "role": "tool",
                "tool_result": {"tool_call_id": "call1", "content": "File written", "is_error": False},
            },
            {"role": "assistant", "content": "Done creating main.py"},
        ],
    }
    sm.save("export_test", agent_data, title="Python Code")

    # 1. Export Markdown (.md)
    md_file = tmp_path / "exported.md"
    res_path = sm.export("export_test", dest_path=md_file)
    assert res_path == md_file
    md_text = md_file.read_text(encoding="utf-8")
    assert "# Conversation: Python Code" in md_text
    assert "### 👤 User" in md_text
    assert "Write a python function" in md_text
    assert "### 🤖 Assistant" in md_text
    assert "> **Tool Call**: `file_write`" in md_text
    assert "👁️ **Tool Output**" in md_text

    # 2. Export JSON (.json)
    json_file = tmp_path / "exported.json"
    res_path = sm.export("export_test", dest_path=json_file)
    assert res_path == json_file
    import json
    parsed = json.loads(json_file.read_text(encoding="utf-8"))
    assert parsed["id"] == "export_test"
    assert len(parsed["agent"]["messages"]) == 4

    # 3. Export Text (.txt)
    txt_file = tmp_path / "exported.txt"
    res_path = sm.export("export_test", dest_path=txt_file)
    assert res_path == txt_file
    txt_text = txt_file.read_text(encoding="utf-8")
    assert "User:\nWrite a python function" in txt_text
    assert "Assistant:\nHere is the code:" in txt_text


def test_main_cli_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    monkeypatch.setattr("agent2.app.tui.SessionManager", lambda: sm)

    agent_data = {
        "name": "assistant",
        "agent_type": "react",
        "messages": [
            {"role": "user", "content": "Hello CLI export"},
            {"role": "assistant", "content": "Export response"},
        ],
    }
    sm.save("cli_exp", agent_data, title="CLI Export Session")

    out_file = tmp_path / "out.md"
    main(["--resume", "cli_exp", "--export", str(out_file)])
    captured = capsys.readouterr().out
    assert f"Conversation exported to: {out_file}" in captured
    assert out_file.exists()
    assert "Hello CLI export" in out_file.read_text(encoding="utf-8")


def test_from_dict_builtin_tool_deduplication() -> None:
    data = {
        "agent_type": "ReActAgent",
        "name": "test_agent",
        "tools": ["file_read", "file_write", "shell_exec"],
        "messages": [],
    }
    restored = BaseAgent.from_dict(data)
    tool_names = [t.name for t in restored.tool_registry.list_tools()]
    assert tool_names == ["file_read", "file_write", "shell_exec"]


@pytest.mark.asyncio
async def test_tui_restore_messages_with_tool_cards(tmp_path: Path) -> None:
    from agent2.app.tui.app import Agent2App, TUIReActAgent
    from agent2.app.tui.widgets.message_list import AssistantMessage, MessageList, UserMessage
    from agent2.app.tui.widgets.tool_card import ToolCard

    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent_data = {
        "name": "assistant",
        "agent_type": "TUIReActAgent",
        "system_prompt": "sys",
        "messages": [
            {"role": "user", "content": "Read test file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "name": "file_read", "arguments": {"path": "test.txt"}}],
            },
            {
                "role": "tool",
                "tool_result": {"tool_call_id": "call_1", "content": "File content 123", "is_error": False},
            },
            {"role": "assistant", "content": "The file contains 123."},
        ],
    }
    sm.save("sess_tools", agent_data, title="Tools Session")

    agent = TUIReActAgent(name="assistant", llm=DummyLLM())
    app = Agent2App(agent=agent, session_manager=sm, resume_session_id="sess_tools")
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)
        u_msgs = list(messages.query(UserMessage))
        a_msgs = list(messages.query(AssistantMessage))
        cards = list(messages.query(ToolCard))

        assert len(u_msgs) == 1
        assert u_msgs[0]._text == "Read test file"

        assert len(cards) == 1
        assert cards[0]._tool_name == "file_read"
        assert cards[0]._initial_result == "File content 123"

        assert len(a_msgs) == 1
        assert a_msgs[0]._content == "The file contains 123."


@pytest.mark.asyncio
async def test_plan_mode_session_save_and_restore(tmp_path: Path) -> None:
    import json
    from agent2.app.tui.app import Agent2App, TUIReActAgent
    from agent2.app.tui.widgets.input_area import ChatInput
    from agent2.app.tui.widgets.message_list import AssistantMessage, MessageList, UserMessage

    plan_json = json.dumps({
        "summary": "Step by step plan",
        "tasks": [{"id": "1", "description": "Write code", "dependencies": [], "context_needed": ""}],
    })

    class PlanLLM(BaseLLM):
        def __init__(self) -> None:
            super().__init__(model="plan-model")

        async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
            return LLMResponse(message=Message.assistant(f"```json\n{plan_json}\n```"))

    sm = SessionManager(session_dir=tmp_path / "sessions", log_dir=tmp_path / "logs")
    agent = TUIReActAgent(name="assistant", llm=PlanLLM())
    app = Agent2App(agent=agent, session_manager=sm, mode="plan")

    async with app.run_test(size=(80, 24)) as pilot:
        chat_input = pilot.app.screen.query_one("#chat-input", ChatInput)
        chat_input.clear()
        chat_input.insert("Build project plan")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        saved = sm.get_latest_session()
        assert saved is not None
        sess_id = saved["id"]

        data = sm.load(sess_id)
        msgs = data["agent"]["messages"]
        user_msgs = [m for m in msgs if m.get("role") == "user"]
        asst_msgs = [m for m in msgs if m.get("role") == "assistant"]

        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "Build project plan"
        assert len(asst_msgs) == 1
        assert "Step by step plan" in asst_msgs[0]["content"]

    resume_agent = TUIReActAgent(name="assistant", llm=PlanLLM())
    resume_app = Agent2App(agent=resume_agent, session_manager=sm, resume_session_id=sess_id, mode="plan")
    async with resume_app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)
        u_msgs = list(messages.query(UserMessage))
        a_msgs = list(messages.query(AssistantMessage))

        assert len(u_msgs) == 1
        assert u_msgs[0]._text == "Build project plan"
        assert len(a_msgs) == 1
        assert "Step by step plan" in a_msgs[0]._content


def test_chat_app_single_turn_undecorated(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from agent2.app.chat import main as chat_main

    dummy_llm = DummyLLM()
    monkeypatch.setattr("agent2.app.chat._build_agent", lambda args: (ReActAgent(name="assistant", llm=dummy_llm), None))

    chat_main(["-p", "Tell me a joke"])
    captured = capsys.readouterr().out
    assert captured == "Dummy response\n"

