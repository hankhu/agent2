"""Plan-and-Execute Agent — separates planning from execution.

The agent first generates a high-level plan (list of steps), then
executes each step sequentially. It can revise the plan dynamically
based on intermediate results.

This pattern improves reliability for complex, multi-step tasks
compared to pure ReAct.
"""

from __future__ import annotations

import json
from typing import Any

from agent2.agent.base import BaseAgent, MaxIterationsExceeded
from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.tools.base import Tool


_PLANNER_PROMPT = """You are a planning agent. Given a task, create a detailed step-by-step plan.

Respond ONLY with a JSON array of strings, where each string is one step.
Example: ["Step 1: Search for ...", "Step 2: Analyse ...", "Step 3: Summarise ..."]

Keep the plan concise (3-7 steps). Each step should be actionable and specific.
"""

_EXECUTOR_PROMPT = """You are a helpful AI assistant executing one step of a larger plan.

The overall task is:
{task}

The full plan is:
{plan}

You are currently executing step {step_number}: {step_description}

Previous step results:
{previous_results}

Execute this step using the available tools. Provide your result clearly.
When done, respond with your findings (no tool calls).
"""

_REPLANNER_PROMPT = """You are a replanning agent. Based on the results so far, decide if the remaining plan needs adjustment.

Original task: {task}
Original plan: {plan}
Completed steps and results: {completed}
Remaining steps: {remaining}

If the remaining plan is still good, respond with: {{"action": "continue"}}
If you need to revise, respond with: {{"action": "revise", "new_remaining_steps": ["step 1", "step 2", ...]}}
"""


class PlannerAgent(BaseAgent):
    """Agent using the Plan-and-Execute pattern.

    1. Generate a plan (list of steps)
    2. Execute each step using a ReAct-style sub-loop
    3. Optionally re-plan after each step

    Usage::

        agent = PlannerAgent("planner", llm=llm, tools=[web_search])
        result = await agent.run("Compare Python and Rust for web development")
    """

    def __init__(
        self,
        name: str,
        *,
        llm: BaseLLM,
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        max_iterations: int | None = None,
        verbose: bool | None = None,
        enable_replan: bool = True,
        max_step_iterations: int = 5,
    ) -> None:
        super().__init__(
            name,
            llm=llm,
            system_prompt=system_prompt or "You are a helpful planning assistant.",
            tools=tools,
            max_iterations=max_iterations,
            verbose=verbose,
        )
        self.enable_replan = enable_replan
        self.max_step_iterations = max_step_iterations

    async def _run_loop(self) -> str:
        """Plan → Execute each step → Synthesise."""
        task = self._messages[-1].content or ""

        # Phase 1: Generate plan
        plan = await self._generate_plan(task)
        self.log.plan(plan)

        # Phase 2: Execute steps
        step_results: list[dict[str, str]] = []

        while plan:
            step_desc = plan.pop(0)
            step_num = len(step_results) + 1
            self.log.plan_step_start(step_num, step_desc)

            result = await self._execute_step(
                task=task,
                plan_overview=[r["step"] for r in step_results] + [step_desc] + plan,
                step_number=step_num,
                step_description=step_desc,
                previous_results=step_results,
            )

            step_results.append({"step": step_desc, "result": result})
            self.log.plan_step_done(step_num)

            # Phase 2.5: Optionally re-plan
            if self.enable_replan and plan:
                plan = await self._maybe_replan(task, step_results, plan)

        # Phase 3: Synthesise final answer
        return await self._synthesise(task, step_results)

    async def _generate_plan(self, task: str) -> list[str]:
        """Use the LLM to create an execution plan."""
        response = await self.llm.chat([
            Message.system(_PLANNER_PROMPT),
            Message.user(task),
        ])

        content = response.content or "[]"
        # Extract JSON from possible markdown code blocks
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        try:
            plan = json.loads(content.strip())
            if isinstance(plan, list):
                return [str(s) for s in plan]
        except json.JSONDecodeError:
            pass

        # Fallback: split by newlines
        return [line.strip() for line in content.strip().split("\n") if line.strip()]

    async def _execute_step(
        self,
        task: str,
        plan_overview: list[str],
        step_number: int,
        step_description: str,
        previous_results: list[dict[str, str]],
    ) -> str:
        """Execute a single plan step using a mini ReAct loop."""
        prev_text = "\n".join(
            f"Step {i+1} ({r['step']}): {r['result'][:200]}"
            for i, r in enumerate(previous_results)
        ) or "None yet."

        system = _EXECUTOR_PROMPT.format(
            task=task,
            plan="\n".join(f"{i+1}. {s}" for i, s in enumerate(plan_overview)),
            step_number=step_number,
            step_description=step_description,
            previous_results=prev_text,
        )

        messages = [
            Message.system(system),
            Message.user(f"Execute step {step_number}: {step_description}"),
        ]

        tool_schemas = self.tool_registry.list_schemas() or None

        for _ in range(self.max_step_iterations):
            response = await self.llm.chat(messages, tools=tool_schemas)

            if response.has_tool_calls:
                if response.content:
                    self.log.thought(response.content)
                messages.append(response.message)
                tool_results = await self._execute_tool_calls(response.tool_calls)
                messages.extend(tool_results)
                continue

            return response.content or ""

        return "(Step execution reached iteration limit)"

    async def _maybe_replan(
        self,
        task: str,
        completed: list[dict[str, str]],
        remaining: list[str],
    ) -> list[str]:
        """Ask the LLM if the remaining plan needs revision."""
        prompt = _REPLANNER_PROMPT.format(
            task=task,
            plan="(see completed + remaining)",
            completed=json.dumps(completed, ensure_ascii=False, indent=2),
            remaining=json.dumps(remaining, ensure_ascii=False),
        )

        response = await self.llm.chat([
            Message.system("You are a replanning agent. Respond in JSON only."),
            Message.user(prompt),
        ])

        content = response.content or ""
        try:
            data = json.loads(content.strip())
            if data.get("action") == "revise" and "new_remaining_steps" in data:
                new_plan = [str(s) for s in data["new_remaining_steps"]]
                self.log.plan(new_plan)
                return new_plan
        except (json.JSONDecodeError, AttributeError):
            pass

        return remaining

    async def _synthesise(
        self, task: str, step_results: list[dict[str, str]]
    ) -> str:
        """Synthesise a final answer from all step results."""
        results_text = "\n\n".join(
            f"### Step {i+1}: {r['step']}\n{r['result']}"
            for i, r in enumerate(step_results)
        )

        response = await self.llm.chat([
            Message.system(
                "Synthesise all the step results into a clear, comprehensive final answer. "
                "Be concise but thorough."
            ),
            Message.user(
                f"Original task: {task}\n\n"
                f"Step results:\n{results_text}\n\n"
                f"Provide a final comprehensive answer."
            ),
        ])

        answer = response.content or ""
        self.log.final_answer(answer)
        return answer
