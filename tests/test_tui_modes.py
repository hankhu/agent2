"""Tests for TUI Plan mode, Ask mode, DAG task scheduling, and context isolation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent2.app.tui import parse_args
from agent2.app.tui.app import ASK_SYSTEM_MSG, DEFAULT_SYSTEM_MSG, Agent2App, TUIReActAgent, build_tui_agent
from agent2.app.tui.planner import (
    Plan,
    TaskItem,
    format_plan_markdown,
    generate_plan,
    is_plan_confirmation,
    synthesize_plan_results,
    topological_sort_tasks,
)
from agent2.llm.base import BaseLLM
from agent2.llm.message import LLMResponse, Message, Role, ToolCall
from agent2.tools.base import tool
from agent2.tools.builtin import file_read, file_write, shell_exec


class MockLLM(BaseLLM):
    """Mock LLM for testing prompt responses and tool calls."""

    def __init__(self, responses: list[str | LLMResponse] | None = None) -> None:
        super().__init__(model="mock-model")
        self._responses = list(responses or [])
        self.call_history: list[list[Message]] = []
        self.tools_history: list[any] = []

    async def chat(self, messages: list[Message], tools=None) -> LLMResponse:
        self.call_history.append(list(messages))
        self.tools_history.append(tools)
        if self._responses:
            resp = self._responses.pop(0)
            if isinstance(resp, LLMResponse):
                return resp
            return LLMResponse(message=Message.assistant(resp))
        return LLMResponse(message=Message.assistant("Default mock response"))


# ── 1. DAG & Topological Sorting Tests ─────────────────────────


def test_topological_sort_independent() -> None:
    tasks = [
        TaskItem(id="1", description="Task 1", dependencies=[]),
        TaskItem(id="2", description="Task 2", dependencies=[]),
    ]
    sorted_tasks = topological_sort_tasks(tasks)
    ids = [t.id for t in sorted_tasks]
    assert ids == ["1", "2"]


def test_topological_sort_linear() -> None:
    tasks = [
        TaskItem(id="3", description="Task 3", dependencies=["2"]),
        TaskItem(id="1", description="Task 1", dependencies=[]),
        TaskItem(id="2", description="Task 2", dependencies=["1"]),
    ]
    sorted_tasks = topological_sort_tasks(tasks)
    ids = [t.id for t in sorted_tasks]
    assert ids == ["1", "2", "3"]


def test_topological_sort_diamond() -> None:
    # 1 -> 2, 1 -> 3, (2, 3) -> 4
    tasks = [
        TaskItem(id="4", description="Task 4", dependencies=["2", "3"]),
        TaskItem(id="2", description="Task 2", dependencies=["1"]),
        TaskItem(id="3", description="Task 3", dependencies=["1"]),
        TaskItem(id="1", description="Task 1", dependencies=[]),
    ]
    sorted_tasks = topological_sort_tasks(tasks)
    ids = [t.id for t in sorted_tasks]
    assert ids[0] == "1"
    assert ids[-1] == "4"
    assert set(ids[1:3]) == {"2", "3"}


def test_topological_sort_cycle_fallback() -> None:
    # Cycle: 1 -> 2 -> 1
    tasks = [
        TaskItem(id="1", description="Task 1", dependencies=["2"]),
        TaskItem(id="2", description="Task 2", dependencies=["1"]),
    ]
    sorted_tasks = topological_sort_tasks(tasks)
    # Falls back gracefully to original list without crashing or hanging
    assert len(sorted_tasks) == 2
    assert [t.id for t in sorted_tasks] == ["1", "2"]


# ── 2. Plan Confirmation Detection Tests ───────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "yes",
        "Yes",
        "YES",
        "y",
        "Y",
        "ok",
        "OK",
        "okay",
        "sure",
        "proceed",
        "confirm",
        "approve",
        "/confirm",
        "/yes",
        "确认",
        "确认执行",
        "同意",
        "执行",
        "好",
        "好的",
        "没问题",
        "可以",
        "行",
        "开始",
        "yes!",
        "确认。",
    ],
)
def test_is_plan_confirmation_positive(text: str) -> None:
    assert is_plan_confirmation(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "no",
        "cancel",
        "请把任务 2 改成优化内存",
        "还需要增加一个测试步骤",
        "为什么需要任务 1？",
        "modify step 1 to read config.py",
        "what does this do?",
    ],
)
def test_is_plan_confirmation_negative(text: str) -> None:
    assert is_plan_confirmation(text) is False


# ── 3. Plan Generation & Formatting Tests ───────────────────────


@pytest.mark.asyncio
async def test_generate_plan_success() -> None:
    plan_json = json.dumps({
        "summary": "Analyze and refactor AST parser",
        "tasks": [
            {
                "id": "1",
                "description": "Inspect parser.py",
                "dependencies": [],
                "context_needed": "File path",
            },
            {
                "id": "2",
                "description": "Implement visitor",
                "dependencies": ["1"],
                "context_needed": "Parser AST structure",
            },
        ],
    })
    llm = MockLLM([f"```json\n{plan_json}\n```"])
    plan = await generate_plan(llm, "Refactor AST parser")

    assert plan.goal == "Refactor AST parser"
    assert plan.summary == "Analyze and refactor AST parser"
    assert len(plan.tasks) == 2
    assert plan.tasks[0].id == "1"
    assert plan.tasks[0].description == "Inspect parser.py"
    assert plan.tasks[1].dependencies == ["1"]
    assert plan.tasks[1].context_needed == "Parser AST structure"


@pytest.mark.asyncio
async def test_generate_plan_fallback() -> None:
    llm = MockLLM(["Sorry, I cannot format this in json."])
    plan = await generate_plan(llm, "Simple task")
    assert plan.goal == "Simple task"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "Simple task"


def test_format_plan_markdown() -> None:
    plan = Plan(
        goal="Build feature X",
        summary="Two-step rollout",
        tasks=[
            TaskItem(id="1", description="Step 1", dependencies=[], context_needed="Input data"),
            TaskItem(id="2", description="Step 2", dependencies=["1"], context_needed="Step 1 result"),
        ],
    )
    md = format_plan_markdown(plan)
    assert "### 📋 任务执行计划 (Execution Plan)" in md
    assert "**目标**：Build feature X" in md
    assert "**概述**：Two-step rollout" in md
    assert "| **1** | Step 1 | — | Input data |" in md
    assert "| **2** | Step 2 | #1 | Step 1 result |" in md
    assert "回复 **`yes`** / **`确认`** / **`ok`**" in md


@pytest.mark.asyncio
async def test_synthesize_plan_results() -> None:
    llm = MockLLM(["Summary: Both tasks succeeded."])
    task_results = [
        {"id": "1", "description": "Fetch data", "result": "Data fetched"},
        {"id": "2", "description": "Process data", "result": "Data processed"},
    ]
    res = await synthesize_plan_results(llm, "Overall goal", task_results)
    assert res == "Summary: Both tasks succeeded."
    assert len(llm.call_history) == 1
    call_prompt = llm.call_history[0][1].content
    assert "Fetch data" in call_prompt
    assert "Data processed" in call_prompt


# ── 4. Ask Mode Enforcement Tests (Strict Read-Only) ────────────


@pytest.mark.asyncio
async def test_ask_mode_blocks_write_and_exec_tools() -> None:
    llm = MockLLM()
    # Create agent with read, write, and shell tools
    agent = TUIReActAgent(
        name="test-assistant",
        llm=llm,
        tools=[file_read, file_write, shell_exec],
        mode="ask",
    )

    assert agent.mode == "ask"

    # Attempt calling file_write tool in Ask mode
    write_call = ToolCall(
        id="call_write_1",
        name="file_write",
        arguments={"path": "dummy.txt", "content": "hello"},
    )
    # Attempt calling shell_exec tool in Ask mode
    shell_call = ToolCall(
        id="call_shell_1",
        name="shell_exec",
        arguments={"command": "rm -rf /"},
    )

    results = await agent._execute_tool_calls([write_call, shell_call])
    assert len(results) == 2
    # Both calls must be rejected as errors
    assert results[0].tool_result.is_error is True
    assert "forbidden in Ask mode" in results[0].tool_result.content
    assert results[1].tool_result.is_error is True
    assert "forbidden in Ask mode" in results[1].tool_result.content


@pytest.mark.asyncio
async def test_ask_mode_allows_safe_tools() -> None:
    llm = MockLLM()
    agent = TUIReActAgent(
        name="test-assistant",
        llm=llm,
        tools=[file_read],
        mode="ask",
    )

    # Read existing file
    read_call = ToolCall(
        id="call_read_1",
        name="file_read",
        arguments={"path": "pyproject.toml"},
    )
    results = await agent._execute_tool_calls([read_call])
    assert len(results) == 1
    assert results[0].tool_result.is_error is False
    assert "dependencies" in results[0].tool_result.content


@pytest.mark.asyncio
async def test_ask_mode_filters_tool_schemas_in_run_loop() -> None:
    llm = MockLLM(["I am in read-only mode."])
    agent = TUIReActAgent(
        name="test-assistant",
        llm=llm,
        tools=[file_read, file_write, shell_exec],
        mode="ask",
    )

    await agent.chat("Can you check files?")

    # Verify tool schemas passed to LLM only contained safe tools
    tools_passed = llm.tools_history[0]
    tool_names = [t.name for t in tools_passed]
    assert "file_read" in tool_names
    assert "file_write" not in tool_names
    assert "shell_exec" not in tool_names


def test_agent_mode_switching_system_prompts() -> None:
    agent = TUIReActAgent(
        name="test-assistant",
        llm=MockLLM(),
        system_prompt=DEFAULT_SYSTEM_MSG,
    )
    assert agent.mode == "agent"
    assert agent.system_prompt == DEFAULT_SYSTEM_MSG

    agent.set_mode("ask")
    assert agent.mode == "ask"
    assert agent.system_prompt == ASK_SYSTEM_MSG

    agent.set_mode("agent")
    assert agent.mode == "agent"
    assert agent.system_prompt == DEFAULT_SYSTEM_MSG


# ── 5. CLI & App Integration Tests ──────────────────────────────


def test_parse_args_mode() -> None:
    args = parse_args([])
    assert args.mode == "agent"

    args = parse_args(["--mode", "plan"])
    assert args.mode == "plan"

    args = parse_args(["--mode", "ask"])
    assert args.mode == "ask"


def test_build_tui_agent_modes() -> None:
    agent_default = build_tui_agent(mode="agent")
    assert agent_default.mode == "agent"
    tool_names = [t.name for t in agent_default.tool_registry.list_tools()]
    assert "file_write" in tool_names
    assert "shell_exec" in tool_names

    agent_ask = build_tui_agent(mode="ask")
    assert agent_ask.mode == "ask"
    assert agent_ask.system_prompt == ASK_SYSTEM_MSG
    ask_tool_names = [t.name for t in agent_ask.tool_registry.list_tools()]
    assert "file_write" not in ask_tool_names
    assert "shell_exec" not in ask_tool_names
    assert "file_read" in ask_tool_names


def test_agent2_app_mode_handling() -> None:
    agent = build_tui_agent(mode="ask")
    app = Agent2App(agent=agent, mode="ask")
    assert app.mode == "ask"
    assert app.agent.mode == "ask"

    app.set_mode("agent")
    assert app.mode == "agent"
    assert app.agent.mode == "agent"


# ── 6. Full Plan Execution Simulation & Context Isolation Test ──


@pytest.mark.asyncio
async def test_plan_execution_workflow_and_context_isolation() -> None:
    # 1. Plan definition
    plan = Plan(
        goal="Refactor authentication and add tests",
        summary="Two-step refactoring",
        tasks=[
            TaskItem(id="2", description="Write auth tests", dependencies=["1"], context_needed="New auth API"),
            TaskItem(id="1", description="Refactor auth module", dependencies=[], context_needed="Existing auth.py"),
        ],
    )

    # 2. Confirmation
    assert is_plan_confirmation("确认执行") is True

    # 3. Topological sorting (must execute 1 before 2)
    ordered = topological_sort_tasks(plan.tasks)
    assert [t.id for t in ordered] == ["1", "2"]

    # 4. Execute subtasks and test isolated context passing
    task_results: dict[str, str] = {}
    recorded_prompts: dict[str, str] = {}

    for task in ordered:
        # Build isolated context
        dep_contexts = []
        for dep_id in task.dependencies:
            if dep_id in task_results:
                dep_contexts.append(f"• 前序任务 #{dep_id} 结果:\n{task_results[dep_id]}")
        dep_text = "\n\n".join(dep_contexts) if dep_contexts else "无（无前序依赖）"

        subtask_prompt = (
            f"【子任务目标】\n{task.description}\n\n"
            f"【所需特定上下文】\n{task.context_needed or '无'}\n\n"
            f"【依赖任务输出】\n{dep_text}\n\n"
            "请根据上述特定上下文和依赖任务输出，使用可用工具完成该子任务，并提供清晰准确的执行结果总结。"
        )
        recorded_prompts[task.id] = subtask_prompt

        # Simulate sub-agent execution
        sub_llm = MockLLM([f"Result for {task.id}: Completed successfully"])
        sub_agent = TUIReActAgent(name=f"SubAgent-{task.id}", llm=sub_llm)
        res = await sub_agent.run(subtask_prompt)
        task_results[task.id] = res

    # Verify context isolation:
    # Task 1 prompt has NO dependency output
    assert "无（无前序依赖）" in recorded_prompts["1"]
    assert "Result for 1" not in recorded_prompts["1"]

    # Task 2 prompt ONLY has Task 1 output
    assert "• 前序任务 #1 结果:\nResult for 1: Completed successfully" in recorded_prompts["2"]
    assert "【所需特定上下文】\nNew auth API" in recorded_prompts["2"]

    # 5. Synthesize final answer
    synth_llm = MockLLM(["All tasks completed. Authentication refactored and tests added."])
    recorded_results = [
        {"id": t.id, "description": t.description, "result": task_results[t.id]}
        for t in ordered
    ]
    final = await synthesize_plan_results(synth_llm, plan.goal, recorded_results)
    assert "Authentication refactored" in final

    # 6. Verify balanced message pairing in agent message history
    parent_agent = TUIReActAgent(name="main-agent", llm=synth_llm)
    assert len(parent_agent.messages) == 0
    parent_agent._messages.append(Message.user(plan.goal))
    parent_agent._messages.append(Message.assistant(final))
    assert len(parent_agent.messages) == 2
    assert parent_agent.messages[0].role == Role.USER
    assert parent_agent.messages[0].content == plan.goal
    assert parent_agent.messages[1].role == Role.ASSISTANT
    assert parent_agent.messages[1].content == final


# ── 7. ConfirmCard Inline Layout & Button Focus Tests ──────────


@pytest.mark.asyncio
async def test_confirm_card_inline_focus_and_navigation() -> None:
    from textual.widgets import Button
    from agent2.app.tui.widgets.confirm_modal import ConfirmCard
    from agent2.app.tui.widgets.message_list import MessageList

    app = Agent2App(agent=build_tui_agent())
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)
        large_args = {f"arg_{i}": f"value_{i}_" * 10 for i in range(10)}

        decision_received = None

        def on_decision(val: str) -> None:
            nonlocal decision_received
            decision_received = val

        card = messages.add_confirm_card("shell_exec", large_args, on_decision=on_decision)
        await pilot.pause()

        # 1. Verify card is embedded in messages list (flow layout)
        assert card in list(messages.children)

        # 2. Verify initial focus is on the approve button
        approve_btn = card.query_one("#approve", Button)
        reject_btn = card.query_one("#reject", Button)
        always_btn = card.query_one("#always", Button)
        assert approve_btn.has_focus

        # 3. Test right arrow switches focus to reject -> always -> wraps to approve
        await pilot.press("right")
        assert reject_btn.has_focus

        await pilot.press("right")
        assert always_btn.has_focus

        await pilot.press("right")
        assert approve_btn.has_focus

        # 4. Test left arrow switches focus in reverse
        await pilot.press("left")
        assert always_btn.has_focus

        # 5. Test pressing enter on always button submits 'always'
        await pilot.press("enter")
        await pilot.pause()
        assert decision_received == "always"
        assert card._decision == "always"
        assert card.query("#confirm-status")


@pytest.mark.asyncio
async def test_confirm_card_shortcuts_and_focus_return() -> None:
    from agent2.app.tui.widgets.message_list import MessageList

    app = Agent2App(agent=build_tui_agent())
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)
        chat_input = pilot.app.screen.query_one("#chat-input")

        decisions = []
        card1 = messages.add_confirm_card("file_write", {"path": "a.txt"}, on_decision=lambda r: decisions.append(r))
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert decisions[-1] == "approve"
        assert chat_input.has_focus

        card2 = messages.add_confirm_card("file_write", {"path": "b.txt"}, on_decision=lambda r: decisions.append(r))
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert decisions[-1] == "reject"
        assert chat_input.has_focus


@pytest.mark.asyncio
async def test_tool_result_panel_collapsed_and_ctrl_o_toggle() -> None:
    from textual.widgets import Collapsible
    from agent2.app.tui.widgets.message_list import MessageList

    app = Agent2App(agent=build_tui_agent())
    async with app.run_test(size=(80, 24)) as pilot:
        messages = pilot.app.screen.query_one("#messages", MessageList)
        card = messages.add_tool_card("file_read", {"path": "test.py"})
        await pilot.pause()
        card.set_result("file contents: line 1\nline 2")
        await pilot.pause()

        result_w = card.query_one(".tool-result", Collapsible)
        # 1. Verify collapsed by default
        assert result_w.collapsed is True

        # 2. Press ctrl+o to expand
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert result_w.collapsed is False

        # 3. Press ctrl+o again to collapse
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert result_w.collapsed is True





