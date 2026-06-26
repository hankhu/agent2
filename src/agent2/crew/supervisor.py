"""Supervisor Crew — a supervisor agent delegates to worker agents.

The supervisor decides which worker to invoke based on the task,
collects results, and synthesises a final answer. This pattern
uses the LLM's tool-calling ability to select workers dynamically.
"""

from __future__ import annotations

import json
from typing import Any

from agent2.agent.base import BaseAgent
from agent2.crew.base import BaseCrew
from agent2.llm.base import BaseLLM
from agent2.llm.message import Message, ToolSchema, ToolParameter


class SupervisorCrew(BaseCrew):
    """Supervisor-worker multi-agent orchestration.

    A supervisor LLM decides which worker agent to invoke, similar to
    a team lead delegating tasks. Workers are exposed as "tools" to the
    supervisor.

    Parameters
    ----------
    name : str
        Crew name.
    agents : list[BaseAgent]
        Worker agents.
    supervisor_llm : BaseLLM
        LLM for the supervisor (can differ from worker LLMs).
    max_delegations : int
        Maximum number of worker invocations.

    Usage::

        crew = SupervisorCrew(
            "team",
            agents=[researcher, coder, writer],
            supervisor_llm=llm,
        )
        result = await crew.run("Build a simple web scraper")
    """

    def __init__(
        self,
        name: str,
        *,
        agents: list[BaseAgent],
        supervisor_llm: BaseLLM,
        max_delegations: int = 10,
        verbose: bool = True,
    ) -> None:
        super().__init__(name, agents=agents, verbose=verbose)
        self.supervisor_llm = supervisor_llm
        self.max_delegations = max_delegations
        self._agent_map = {a.name: a for a in agents}

    async def _orchestrate(self, task: str) -> str:
        """Supervisor delegates to workers via tool calling."""
        # Build tool schemas representing each worker agent
        agent_tools = self._build_agent_tools()

        system_prompt = self._build_supervisor_prompt()

        messages: list[Message] = [
            Message.system(system_prompt),
            Message.user(task),
        ]

        for _ in range(self.max_delegations):
            response = await self.supervisor_llm.chat(messages, tools=agent_tools)

            if response.has_tool_calls:
                if response.content:
                    self.log.thought(response.content)
                messages.append(response.message)

                for tc in response.tool_calls:
                    agent_name = tc.name.replace("delegate_to_", "")
                    agent_task = tc.arguments.get("task", task)

                    agent = self._agent_map.get(agent_name)
                    if agent is None:
                        result = f"Error: Agent '{agent_name}' not found."
                    else:
                        self.log.delegate(self.name, agent_name, agent_task)
                        result = await agent.run(agent_task)
                        self.log.agent_message(agent_name, result)

                    messages.append(Message.tool(tc.id, result))
                continue

            # Supervisor gives final answer
            final = response.content or ""
            self.log.final_answer(final)
            return final

        return "(Supervisor exceeded maximum delegations)"

    def _build_agent_tools(self) -> list[ToolSchema]:
        """Create tool schemas representing each worker agent."""
        tools: list[ToolSchema] = []
        for agent in self.agents:
            tools.append(
                ToolSchema(
                    name=f"delegate_to_{agent.name}",
                    description=(
                        f"Delegate a sub-task to the '{agent.name}' agent. "
                        f"This agent's role: {agent.system_prompt[:200]}"
                    ),
                    parameters=[
                        ToolParameter(
                            name="task",
                            type="string",
                            description="The specific sub-task to delegate to this agent.",
                            required=True,
                        )
                    ],
                )
            )
        return tools

    def _build_supervisor_prompt(self) -> str:
        """Build the supervisor's system prompt."""
        agent_descriptions = "\n".join(
            f"- **{a.name}**: {a.system_prompt[:100]}"
            for a in self.agents
        )
        return (
            "You are a supervisor managing a team of AI agents. "
            "Your job is to break down the user's task and delegate "
            "sub-tasks to the most appropriate team members.\n\n"
            f"Available team members:\n{agent_descriptions}\n\n"
            "Use the delegate tools to assign work. Once you have "
            "enough information from your team, provide a final "
            "comprehensive answer."
        )
