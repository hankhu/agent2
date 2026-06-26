"""Base Agent class — the foundation for all agent types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.tools.base import Tool
from agent2.tools.registry import ToolRegistry
from agent2.utils.config import settings
from agent2.utils.logging import AgentLogger


class BaseAgent(ABC):
    """Abstract base class for all agents.

    An agent combines an LLM with tools and a system prompt to perform
    tasks through an iterative reasoning loop.

    Parameters
    ----------
    name : str
        Human-readable agent name.
    llm : BaseLLM
        The language model to use for reasoning.
    system_prompt : str
        Instructions defining the agent's role and behaviour.
    tools : list[Tool] | None
        Tools available to this agent.
    max_iterations : int
        Safety limit for the reasoning loop.
    verbose : bool
        Enable detailed logging of the reasoning process.
    """

    def __init__(
        self,
        name: str,
        *,
        llm: BaseLLM,
        system_prompt: str = "You are a helpful AI assistant.",
        tools: list[Tool] | None = None,
        max_iterations: int | None = None,
        verbose: bool | None = None,
    ) -> None:
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations or settings.agent_max_iterations
        self.verbose = verbose if verbose is not None else settings.agent_verbose

        # Set up tool registry
        self.tool_registry = ToolRegistry()
        if tools:
            for t in tools:
                self.tool_registry.register(t)

        # Set up logger
        self.log = AgentLogger(name, verbose=self.verbose)

        # Conversation history for the current run
        self._messages: list[Message] = []

    # ── Public API ──────────────────────────────────────────────────

    async def run(self, task: str) -> str:
        """Execute a task and return the final answer.

        Parameters
        ----------
        task : str
            The user's task or question.

        Returns
        -------
        str
            The agent's final response.
        """
        self.log.start(task)

        # Initialize conversation
        self._messages = [
            Message.system(self.system_prompt),
            Message.user(task),
        ]

        try:
            result = await self._run_loop()
        except MaxIterationsExceeded:
            result = (
                f"I was unable to complete the task within {self.max_iterations} steps. "
                f"Here is what I've done so far based on the conversation."
            )
            self.log.observation(result, is_error=True)

        self.log.finish(result)
        return result

    # ── Abstract method for subclasses ──────────────────────────────

    @abstractmethod
    async def _run_loop(self) -> str:
        """The core reasoning loop. Subclasses implement this.

        Returns the final answer string.
        """
        ...

    # ── Helpers ─────────────────────────────────────────────────────

    async def _execute_tool_calls(self, tool_calls: list[Any]) -> list[Message]:
        """Execute a list of tool calls and return result messages."""
        results: list[Message] = []
        for tc in tool_calls:
            self.log.action(tc.name, tc.arguments)
            output = await self.tool_registry.execute(tc.name, **tc.arguments)
            is_error = output.startswith("Error")
            self.log.observation(output, is_error=is_error)
            results.append(Message.tool(tc.id, output, is_error=is_error))
        return results

    def __repr__(self) -> str:
        tools = [t.name for t in self.tool_registry.list_tools()]
        return f"{self.__class__.__name__}(name={self.name!r}, llm={self.llm!r}, tools={tools})"


class MaxIterationsExceeded(Exception):
    """Raised when agent exceeds its maximum iteration count."""
    pass
