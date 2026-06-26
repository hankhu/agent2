"""Tool system — define, register, and execute tools for LLM agents.

Quick start::

    from agent2.tools import tool, ToolRegistry

    @tool(description="Calculate a math expression")
    def calculate(expression: str) -> str:
        return str(eval(expression))

    registry = ToolRegistry()
    registry.register(calculate)
"""

from agent2.tools.base import Tool, tool
from agent2.tools.registry import ToolRegistry

__all__ = ["Tool", "tool", "ToolRegistry"]
