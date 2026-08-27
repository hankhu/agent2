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

    # ── Serialization & Persistence ─────────────────────────────────

    def _get_extra_state(self) -> dict[str, Any]:
        """Hook for subclasses to persist additional state."""
        return {}

    def _load_extra_state(self, extra: dict[str, Any]) -> None:
        """Hook for subclasses to restore additional state."""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Serialize the agent state to a dictionary.

        Returns
        -------
        dict[str, Any]
            Serialized agent data including message history.
        """
        return {
            "agent_type": self.__class__.__name__,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "max_iterations": self.max_iterations,
            "verbose": self.verbose,
            "messages": [m.model_dump(exclude_none=True) for m in self._messages],
            "tools": [t.name for t in self.tool_registry.list_tools()],
            "extra": self._get_extra_state(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the agent state to a JSON-formatted string."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, path_or_fp: str | Path | TextIO) -> None:
        """Save the serialized agent state to a file or stream.

        Parameters
        ----------
        path_or_fp : str | Path | TextIO
            File path string, pathlib.Path, or open text file object.
        """
        import json
        from pathlib import Path

        data = self.to_dict()
        if isinstance(path_or_fp, (str, Path)):
            p = Path(path_or_fp)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            json.dump(data, path_or_fp, ensure_ascii=False, indent=2)

    @classmethod
    def _resolve_agent_class(cls, agent_type: str | None) -> type[BaseAgent]:
        """Resolve agent subclass by type name."""
        if cls is not BaseAgent:
            return cls
        if agent_type == "PlannerAgent":
            from agent2.agent.planner import PlannerAgent
            return PlannerAgent
        from agent2.agent.react import ReActAgent
        return ReActAgent

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        llm: BaseLLM | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Restore an agent instance from a dictionary.

        Parameters
        ----------
        data : dict[str, Any]
            Serialized agent data dictionary.
        llm : BaseLLM | None
            Optional LLM instance. If not provided, a default LLM is created.
        tools : list[Tool] | None
            Optional list of Tool instances to bind to the restored agent.
        **kwargs
            Additional arguments passed to the agent constructor.

        Returns
        -------
        BaseAgent
            Restored agent instance with conversation history loaded.
        """
        agent_cls = cls._resolve_agent_class(data.get("agent_type"))
        name = kwargs.pop("name", data.get("name", "agent"))
        system_prompt = kwargs.pop("system_prompt", data.get("system_prompt", "You are a helpful AI assistant."))
        max_iterations = kwargs.pop("max_iterations", data.get("max_iterations"))
        verbose = kwargs.pop("verbose", data.get("verbose"))

        resolved_tools: list[Tool] = []
        if tools:
            resolved_tools.extend(tools)
        else:
            tool_names = set(data.get("tools", []))
            if tool_names:
                try:
                    import agent2.tools.builtin as builtin_module
                    for attr_name in dir(builtin_module):
                        val = getattr(builtin_module, attr_name)
                        if isinstance(val, Tool) and val.name in tool_names:
                            resolved_tools.append(val)
                except Exception:
                    pass

        agent = agent_cls(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            tools=resolved_tools if resolved_tools else None,
            max_iterations=max_iterations,
            verbose=verbose,
            **kwargs,
        )

        extra = data.get("extra", {})
        if extra and hasattr(agent, "_load_extra_state"):
            agent._load_extra_state(extra)

        messages_raw = data.get("messages", [])
        agent._messages = [Message.model_validate(m) for m in messages_raw]
        return agent

    @classmethod
    def from_json(
        cls,
        json_str: str,
        *,
        llm: BaseLLM | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Restore an agent from a JSON string."""
        import json
        data = json.loads(json_str)
        return cls.from_dict(data, llm=llm, tools=tools, **kwargs)

    @classmethod
    def load(
        cls,
        path_or_fp: str | Path | TextIO,
        *,
        llm: BaseLLM | None = None,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Load an agent from a JSON file or file-like object.

        Parameters
        ----------
        path_or_fp : str | Path | TextIO
            File path string, pathlib.Path, or open text file object.
        llm : BaseLLM | None
            Optional LLM instance.
        tools : list[Tool] | None
            Optional list of Tool instances.
        **kwargs
            Additional arguments passed to the agent constructor.

        Returns
        -------
        BaseAgent
            Restored agent instance with full conversation history.
        """
        import json
        from pathlib import Path

        if isinstance(path_or_fp, (str, Path)):
            with open(path_or_fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.load(path_or_fp)
        return cls.from_dict(data, llm=llm, tools=tools, **kwargs)

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

        self.log.finish()
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
