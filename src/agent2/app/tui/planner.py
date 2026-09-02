"""Plan Mode task planning and DAG execution utilities for Agent2 TUI."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

from pydantic import BaseModel, Field

from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.utils.json_helpers import extract_json


class TaskItem(BaseModel):
    """A single subtask within an execution plan."""

    id: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    context_needed: str = ""


class Plan(BaseModel):
    """An execution plan consisting of multiple interdependent tasks."""

    goal: str
    tasks: list[TaskItem] = Field(default_factory=list)
    summary: str = ""


def topological_sort_tasks(tasks: list[TaskItem]) -> list[TaskItem]:
    """Sort tasks in dependency order using Kahn's algorithm.

    If a dependency cycle is detected, returns tasks in their original order.
    """
    task_map: dict[str, TaskItem] = {t.id: t for t in tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    dependents: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        valid_deps = [dep for dep in task.dependencies if dep in task_map]
        in_degree[task.id] = len(valid_deps)
        for dep in valid_deps:
            dependents[dep].append(task.id)

    queue: deque[str] = deque([t_id for t_id, deg in in_degree.items() if deg == 0])
    ordered: list[TaskItem] = []

    while queue:
        current_id = queue.popleft()
        ordered.append(task_map[current_id])
        for dep_id in dependents[current_id]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(ordered) < len(tasks):
        # Cycle detected or unreachable tasks; fallback to original task order
        return list(tasks)

    return ordered


_CONFIRMATION_KEYWORDS = frozenset({
    "yes", "y", "ok", "okay", "sure", "proceed", "go", "confirm", "approve",
    "/confirm", "/yes", "确认", "同意", "执行", "好", "好的", "开始", "没问题",
    "可以", "行", "准了", "通过",
})


def is_plan_confirmation(text: str) -> bool:
    """Check if the user input is a confirmation to execute the plan."""
    cleaned = text.strip().lower().rstrip(".!。！")
    if cleaned in _CONFIRMATION_KEYWORDS:
        return True
    # Check common prefix confirmations (e.g. "确认执行", "可以开始")
    for kw in ("确认", "同意", "执行", "开始", "proceed", "confirm"):
        if cleaned.startswith(kw) and len(cleaned) <= len(kw) + 4:
            return True
    return False


_PLAN_SYSTEM_PROMPT = """You are an expert AI planning coordinator.
Your task is to analyze the user's intent and break it down into an optimal, structured list of subtasks.

Requirements:
1. Each subtask must be specific, actionable, and self-contained.
2. Explicitly specify dependencies between tasks:
   - 'dependencies' must be a list of task IDs that MUST complete before this task can run.
   - If a task can run immediately, 'dependencies' should be [].
3. 'context_needed' should clearly state what information or outputs from previous tasks this subtask needs.
4. Keep the plan concise and effective (typically 2 to 5 subtasks).

You MUST return a JSON object with this exact structure:
{
  "summary": "Brief 1-line overview of the approach",
  "tasks": [
    {
      "id": "1",
      "description": "Specific action to perform",
      "dependencies": [],
      "context_needed": "Context or input required"
    },
    {
      "id": "2",
      "description": "Next action",
      "dependencies": ["1"],
      "context_needed": "Output from task 1"
    }
  ]
}
"""


async def generate_plan(
    llm: BaseLLM,
    user_intent: str,
    existing_plan: Plan | None = None,
    feedback: str | None = None,
) -> Plan:
    """Generate or refine a structured execution plan using the LLM."""
    if existing_plan and feedback:
        user_content = (
            f"Original Goal: {existing_plan.goal}\n\n"
            f"Current Plan:\n{existing_plan.model_dump_json(indent=2)}\n\n"
            f"User Feedback / Adjustments Requested:\n{feedback}\n\n"
            "Please revise the plan accordingly and return the updated JSON."
        )
    else:
        user_content = f"User Intent: {user_intent}"

    response = await llm.chat([
        Message.system(_PLAN_SYSTEM_PROMPT),
        Message.user(user_content),
    ])

    raw = response.content or ""
    try:
        data = extract_json(raw)
        if isinstance(data, dict) and "tasks" in data:
            tasks = [
                TaskItem(
                    id=str(t.get("id", i + 1)),
                    description=str(t.get("description", "")),
                    dependencies=[str(d) for d in t.get("dependencies", [])],
                    context_needed=str(t.get("context_needed", "")),
                )
                for i, t in enumerate(data.get("tasks", []))
            ]
            summary = str(data.get("summary", ""))
            return Plan(
                goal=existing_plan.goal if existing_plan else user_intent,
                tasks=tasks,
                summary=summary,
            )
    except Exception:
        pass

    # Fallback: create a single-task plan
    fallback_task = TaskItem(
        id="1",
        description=user_intent,
        dependencies=[],
        context_needed="User request",
    )
    return Plan(
        goal=user_intent,
        tasks=[fallback_task],
        summary="Direct execution plan",
    )


def format_plan_markdown(plan: Plan) -> str:
    """Format an execution plan into a clean Markdown table with instructions."""
    lines = [
        "### 📋 任务执行计划 (Execution Plan)",
        "",
        f"**目标**：{plan.goal}",
    ]
    if plan.summary:
        lines.append(f"**概述**：{plan.summary}")
    lines.extend([
        "",
        "| # | 子任务 (Task) | 依赖任务 (Dependencies) | 所需上下文 (Context Needed) |",
        "| :--- | :--- | :--- | :--- |",
    ])

    for task in plan.tasks:
        deps = ", ".join(f"#{d}" for d in task.dependencies) if task.dependencies else "—"
        ctx = task.context_needed if task.context_needed else "—"
        lines.append(f"| **{task.id}** | {task.description} | {deps} | {ctx} |")

    lines.extend([
        "",
        "💬 **操作提示**：",
        "- 回复 **`yes`** / **`确认`** / **`ok`** 确认计划并切换至 Agent 模式自动派发执行。",
        "- 或直接输入修改要求对计划进行调整。",
    ])
    return "\n".join(lines)


async def synthesize_plan_results(
    llm: BaseLLM,
    goal: str,
    task_results: list[dict[str, Any]],
) -> str:
    """Synthesize results from all executed subtasks into a comprehensive final answer."""
    results_formatted = []
    for item in task_results:
        task_id = item.get("id", "")
        desc = item.get("description", "")
        res = item.get("result", "")
        results_formatted.append(f"#### 子任务 #{task_id}: {desc}\n{res}")

    content = "\n\n".join(results_formatted)
    prompt = (
        f"用户原始目标:\n{goal}\n\n"
        f"各子任务执行结果:\n{content}\n\n"
        "请根据上述所有子任务的执行结果，给出一个条理清晰、全面准确的最终总结与回答。"
    )

    response = await llm.chat([
        Message.system(
            "You are a helpful assistant synthesizing outputs from multiple subtasks into a unified, high-quality final response."
        ),
        Message.user(prompt),
    ])
    return response.content or "(No final answer generated)"
