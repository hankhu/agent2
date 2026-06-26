"""Tool registry — centralised tool discovery and execution."""

from __future__ import annotations

from typing import Any

from agent2.llm.message import ToolSchema
from agent2.tools.base import Tool


class ToolRegistry:
    """Registry for managing and executing tools.

    Usage::

        registry = ToolRegistry()
        registry.register(my_tool)

        schemas = registry.list_schemas()  # Send to LLM
        result = await registry.execute("my_tool", arg1="value")
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError if name conflicts."""
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                f"Use a unique name or unregister first."
            )
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name, returns None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_schemas(self) -> list[ToolSchema]:
        """Return schemas for all registered tools (for sending to LLM)."""
        return [t.schema for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> str:
        """Execute a tool by name.

        Returns
        -------
        str
            The tool's output as a string, or an error message.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: Tool '{name}' not found. Available tools: {list(self._tools.keys())}"
        return await tool.execute(**kwargs)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        names = list(self._tools.keys())
        return f"ToolRegistry(tools={names})"
