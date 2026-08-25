"""Base Agent class — the foundation for all agent types."""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any, Self

from agent2.llm.base import BaseLLM
from agent2.llm import create_llm
from agent2.llm.message import Message, Role
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
        Human-readable agent name. Defaults to ``"agent"``.
    llm : BaseLLM | None
        The language model to use for reasoning. Defaults to ``create_llm()``.
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
        name: str = "agent",
        *,
        llm: BaseLLM | None = None,
        system_prompt: str = "You are a helpful AI assistant.",
        tools: list[Tool] | None = None,
        max_iterations: int | None = None,
        verbose: bool | None = None,
    ) -> None:
        self.name = name
        self.llm = llm if llm is not None else create_llm()
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

    # ── Properties & State Management ───────────────────────────────

    @property
    def messages(self) -> list[Message]:
        """Return the current conversation message history."""
        return list(self._messages)

    def set_rule(self, rule: str | Message) -> Self:
        """Set or update the system prompt / rule for the agent.

        Parameters
        ----------
        rule : str | Message
            The system prompt text or a system Message object.

        Returns
        -------
        Self
            Returns self to allow method chaining.
        """
        content = rule.content if isinstance(rule, Message) else str(rule)
        content = content or ""
        self.system_prompt = content

        if self._messages:
            if self._messages[0].role == Role.SYSTEM:
                self._messages[0] = Message.system(content)
            else:
                self._messages.insert(0, Message.system(content))
        else:
            self._messages = [Message.system(content)]
        return self

    def reset(self) -> None:
        """Reset the conversation history to initial state."""
        self._messages = [Message.system(self.system_prompt)] if self.system_prompt else []

    def fork(self, name: str | None = None) -> Self:
        """Fork this agent into an independent clone with the same state and history.

        The forked agent inherits conversation history, tools, system prompt,
        and configuration, but subsequent operations on either agent remain isolated.

        Parameters
        ----------
        name : str | None
            New name for the forked agent. Defaults to ``f"{self.name}_fork"``.

        Returns
        -------
        Self
            A new agent instance with cloned state and independent history.
        """
        forked_name = name or f"{self.name}_fork"
        new_agent = copy.copy(self)
        new_agent.name = forked_name
        new_agent.log = AgentLogger(forked_name, verbose=self.verbose)
        new_agent.tool_registry = self.tool_registry.copy()
        new_agent._messages = [m.model_copy(deep=True) for m in self._messages]
        return new_agent

    # ── Public API ──────────────────────────────────────────────────

    async def chat(self, msg: str | Message) -> str:
        """Send a message in a multi-turn conversation and return the assistant response.

        Maintains conversation history across calls.

        Parameters
        ----------
        msg : str | Message
            The user prompt or Message instance.

        Returns
        -------
        str
            The agent's response.
        """
        content = msg if isinstance(msg, str) else (msg.content or "")
        self.log.start(content)

        if not self._messages and self.system_prompt:
            self._messages.append(Message.system(self.system_prompt))

        user_msg = Message.user(msg) if isinstance(msg, str) else msg
        self._messages.append(user_msg)

        try:
            result = await self._run_loop()
        except MaxIterationsExceeded:
            result = (
                f"I was unable to complete the task within {self.max_iterations} steps. "
                f"Here is what I've done so far based on the conversation."
            )
            self.log.observation(result, is_error=True)

        if not self._messages or self._messages[-1].role != Role.ASSISTANT or self._messages[-1].content != result:
            self._messages.append(Message.assistant(result))

        self.log.finish(result)
        return result

    async def run(self, task: str) -> str:
        """Execute a standalone task and return the final answer (resets history).

        Parameters
        ----------
        task : str
            The user's task or question.

        Returns
        -------
        str
            The agent's final response.
        """
        self.reset()
        return await self.chat(task)


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
