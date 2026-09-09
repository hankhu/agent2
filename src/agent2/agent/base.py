"""Base Agent class — the foundation for all agent types."""

from __future__ import annotations

import logging as _logging

import copy
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Self, TextIO

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
        if max_iterations is not None:
            self.max_iterations = max_iterations
        elif "AGENT2_AGENT_MAX_ITERATIONS" in os.environ:
            self.max_iterations = settings.agent_max_iterations
        else:
            try:
                from agent2.app.config import load_config

                self.max_iterations = load_config().max_iterations
            except (KeyError, ValueError, FileNotFoundError, ImportError) as exc:
                _logging.getLogger(__name__).warning(
                    "Failed to load max_iterations from config (%s), using default", exc
                )
                self.max_iterations = settings.agent_max_iterations
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

    def rewind(self, turns: int = 1) -> list[Message]:
        """Rewind the conversation history by a given number of turns (default 1).

        A turn starts with a user message and includes all subsequent assistant
        responses and tool executions.

        If *turns* exceeds the number of user messages in the history, all
        available turns are removed (i.e. the request is silently truncated).

        Parameters
        ----------
        turns : int
            Number of turns to rewind. Defaults to 1.

        Returns
        -------
        list[Message]
            The messages that were removed.
        """
        if turns < 1:
            return []
        removed: list[Message] = []
        for _ in range(turns):
            last_user_idx = None
            for i in range(len(self._messages) - 1, -1, -1):
                if self._messages[i].role == Role.USER:
                    last_user_idx = i
                    break
            if last_user_idx is None:
                break
            removed = self._messages[last_user_idx:] + removed
            self._messages = self._messages[:last_user_idx]
        return removed

    def rewind_to(self, index: int, *, inclusive: bool = False) -> list[Message]:
        """Rewind conversation history to a specific message index.

        Parameters
        ----------
        index : int
            The target message index in ``self._messages``.
        inclusive : bool
            If True, keep the message at index and remove messages after it.
            If False, remove the message at index and all messages after it.

        Returns
        -------
        list[Message]
            The messages that were removed.
        """
        cutoff = index + 1 if inclusive else index
        if cutoff < 0 or cutoff >= len(self._messages):
            return []
        removed = self._messages[cutoff:]
        self._messages = self._messages[:cutoff]
        return removed

    async def compact(self, *, keep_recent_turns: int = 1) -> dict[str, Any]:
        """Compact conversation history by semantically summarizing past turns.

        Preserves system prompt and the specified number of most recent turns
        (default 1), replacing earlier rounds and tool executions with a concise
        semantic summary produced by the LLM.

        Parameters
        ----------
        keep_recent_turns : int
            Number of recent user turns to retain uncompressed.

        Returns
        -------
        dict[str, Any]
            Compaction summary with status, messages_before, messages_after,
            and the summary text.
        """
        user_indices = [
            i for i, m in enumerate(self._messages)
            if m.role == Role.USER
        ]
        if not user_indices or len(user_indices) <= keep_recent_turns:
            return {
                "status": "skipped",
                "reason": "Not enough turns to compact",
                "messages_before": len(self._messages),
                "messages_after": len(self._messages),
                "summary": "",
            }

        split_idx = user_indices[-keep_recent_turns]
        sys_offset = 1 if (self._messages and self._messages[0].role == Role.SYSTEM) else 0

        to_summarize = self._messages[sys_offset:split_idx]
        to_keep = self._messages[split_idx:]

        if not to_summarize:
            return {
                "status": "skipped",
                "reason": "No messages to summarize",
                "messages_before": len(self._messages),
                "messages_after": len(self._messages),
                "summary": "",
            }

        # Build transcript of messages to summarize
        transcript_lines: list[str] = []
        for m in to_summarize:
            role_label = m.role.value.upper()
            if m.role == Role.TOOL and m.tool_result:
                content = m.tool_result.content
                if len(content) > 1000:
                    content = content[:1000] + " ...[truncated]"
                transcript_lines.append(f"[TOOL RESULT ({m.tool_result.tool_call_id})]: {content}")
            elif m.role == Role.ASSISTANT and m.tool_calls:
                call_descs = [f"{tc.name}({tc.arguments})" for tc in m.tool_calls]
                text = m.content or ""
                transcript_lines.append(f"[ASSISTANT]: {text}\n[CALLS]: {', '.join(call_descs)}")
            elif m.content:
                content = m.content
                if len(content) > 2000:
                    content = content[:2000] + " ...[truncated]"
                transcript_lines.append(f"[{role_label}]: {content}")

        history_text = "\n\n".join(transcript_lines)

        summary_prompt = (
            "You are an expert conversation summarizer for an AI assistant.\n"
            "Summarize the preceding conversation history into a structured, concise brief.\n"
            "Preserve:\n"
            "1. User goals, instructions, and constraints.\n"
            "2. Key actions taken, tools invoked, and files modified or inspected.\n"
            "3. Crucial findings, conclusions, and decisions reached.\n"
            "4. Current pending tasks or next steps.\n\n"
            "--- Conversation History ---\n"
            f"{history_text}\n"
            "--- End History ---\n\n"
            "Provide only the concise summary."
        )

        try:
            summary_response = await self.llm.chat([
                Message.system("You are a concise conversation summarizer."),
                Message.user(summary_prompt),
            ])
            summary_content = (summary_response.content or "").strip()
        except Exception as exc:
            summary_content = f"[Compacted {len(to_summarize)} messages: summary generation failed ({exc})]"

        if not summary_content:
            summary_content = f"[Compacted {len(to_summarize)} messages from earlier conversation]"

        # Reassemble messages
        new_messages: list[Message] = []
        if sys_offset > 0:
            new_messages.append(self._messages[0])

        new_messages.append(Message.user(
            f"--- Context Summary of Previous Conversation (compacted) ---\n"
            f"{summary_content}\n"
            f"--- End Summary ---"
        ))
        new_messages.append(Message.assistant(
            "Understood. I have preserved the context from our previous discussion and am ready to proceed."
        ))
        new_messages.extend(to_keep)

        before_count = len(self._messages)
        self._messages = new_messages
        after_count = len(self._messages)

        return {
            "status": "compacted",
            "messages_before": before_count,
            "messages_after": after_count,
            "summary": summary_content,
        }

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
                    seen_names: set[str] = set()
                    for attr_name in dir(builtin_module):
                        val = getattr(builtin_module, attr_name)
                        if (
                            isinstance(val, Tool)
                            and val.name in tool_names
                            and val.name not in seen_names
                        ):
                            resolved_tools.append(val)
                            seen_names.add(val.name)
                except (ImportError, AttributeError) as exc:
                    import logging
                    logging.getLogger(__name__).warning("Failed to load builtin tools: %s", exc)

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
        agent._repair_tool_messages()
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

        self._repair_tool_messages()

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

    def _repair_tool_messages(self) -> None:
        """Ensure every assistant ``tool_calls`` message has tool responses.

        OpenAI-compatible APIs require each ``tool_call_id`` from an assistant
        message to be answered by a following ``tool`` message.  This repairs
        histories that may have been interrupted by an error/cancellation or
        loaded from an older/incomplete session file.
        """
        messages = self._messages
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role == Role.ASSISTANT and msg.tool_calls:
                expected = {tc.id for tc in msg.tool_calls}
                j = i + 1
                found: set[str] = set()
                while j < len(messages) and messages[j].role == Role.TOOL:
                    if messages[j].tool_result is not None:
                        found.add(messages[j].tool_result.tool_call_id)
                    j += 1
                missing = expected - found
                if missing:
                    insert_at = j
                    for tool_call_id in sorted(missing):
                        messages.insert(
                            insert_at,
                            Message.tool(
                                tool_call_id,
                                "Tool execution did not return a result.",
                                is_error=True,
                            ),
                        )
                        insert_at += 1
                    i = insert_at
                    continue
                i = j
            else:
                i += 1

    async def _execute_tool_calls(self, tool_calls: list[Any]) -> list[Message]:
        """Execute a list of tool calls and return result messages.

        Every tool call always produces a tool result, even when execution
        raises, so the conversation history remains valid for OpenAI-compatible
        APIs (an assistant ``tool_calls`` message must be followed by one tool
        message per ``tool_call_id``).
        """
        results: list[Message] = []
        for tc in tool_calls:
            self.log.action(tc.name, tc.arguments)
            try:
                output = await self.tool_registry.execute(tc.name, **tc.arguments)
            except Exception as exc:
                output = f"Error executing {tc.name}: {exc}"
                is_error = True
            else:
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
