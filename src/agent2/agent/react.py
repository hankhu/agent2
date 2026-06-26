"""ReAct Agent — Reasoning + Acting pattern.

The ReAct loop alternates between:
  1. **Thought**: The LLM reasons about what to do next
  2. **Action**: The LLM calls a tool
  3. **Observation**: The tool result is fed back to the LLM
  4. **Repeat** until the LLM provides a final answer (no tool calls)

Reference: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2022)
"""

from __future__ import annotations

from typing import Any

from agent2.agent.base import BaseAgent, MaxIterationsExceeded
from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.tools.base import Tool


_DEFAULT_REACT_PROMPT = """You are a helpful AI assistant that can use tools to accomplish tasks.

When you need information or need to perform an action, use the available tools.
Think step by step about what you need to do.
When you have gathered enough information to answer the user's question, provide your final answer directly without calling any more tools.

Important:
- Always think before acting.
- Use tools when you need external information or capabilities.
- When you're ready to give the final answer, respond with text only (no tool calls).
"""


class ReActAgent(BaseAgent):
    """Agent implementing the ReAct (Reasoning + Acting) pattern.

    This is the most fundamental agent type. It iteratively reasons
    and acts until it arrives at a final answer.

    Usage::

        from agent2.llm import create_llm
        from agent2.agent import ReActAgent
        from agent2.tools.builtin import web_search

        llm = create_llm("openai", model="gpt-4o-mini")
        agent = ReActAgent("researcher", llm=llm, tools=[web_search])
        result = await agent.run("What is the capital of France?")
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
    ) -> None:
        super().__init__(
            name,
            llm=llm,
            system_prompt=system_prompt or _DEFAULT_REACT_PROMPT,
            tools=tools,
            max_iterations=max_iterations,
            verbose=verbose,
        )

    async def _run_loop(self) -> str:
        """Execute the ReAct loop: Thought → Action → Observation → repeat."""
        tool_schemas = self.tool_registry.list_schemas() or None

        for iteration in range(1, self.max_iterations + 1):
            # Ask the LLM to think and optionally call tools
            response = await self.llm.chat(
                self._messages,
                tools=tool_schemas,
            )

            # If the LLM wants to call tools → Action + Observation
            if response.has_tool_calls:
                # Log the thinking (if any content accompanies tool calls)
                if response.content:
                    self.log.thought(response.content)

                # Record the assistant message with tool calls
                self._messages.append(response.message)

                # Execute each tool call
                tool_results = await self._execute_tool_calls(response.tool_calls)
                self._messages.extend(tool_results)
                continue

            # No tool calls → this is the final answer
            final_answer = response.content or ""
            self.log.final_answer(final_answer)
            return final_answer

        # Exceeded max iterations
        raise MaxIterationsExceeded(
            f"Agent '{self.name}' exceeded {self.max_iterations} iterations"
        )
