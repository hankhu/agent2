"""Tool base class and @tool decorator.

Provides a type-safe mechanism to define tools that LLMs can invoke.
Tool schemas are auto-generated from Python type hints.

Usage::

    from agent2.tools import tool

    @tool(description="Add two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    # The decorated function is now a Tool instance
    schema = add.schema        # ToolSchema for LLM
    result = await add(a=1, b=2)  # Execute the tool
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, get_type_hints

from agent2.llm.message import ToolParameter, ToolSchema


# ── Python type → JSON Schema type mapping ──────────────────────────

_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json(py_type: Any) -> str:
    """Map a Python type annotation to a JSON Schema type string."""
    # Handle Optional, Union, etc.
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        # list[X] → "array"
        if origin is list:
            return "array"
        # dict[X, Y] → "object"
        if origin is dict:
            return "object"

    return _TYPE_MAP.get(py_type, "string")


# ── Tool class ──────────────────────────────────────────────────────


class Tool:
    """Wraps a callable function as a tool with auto-generated schema.

    Attributes
    ----------
    name : str
        Tool name (defaults to function name).
    description : str
        Human-readable description for the LLM.
    schema : ToolSchema
        Auto-generated schema from function signature.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self.func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or ""
        self._is_async = asyncio.iscoroutinefunction(func)
        self.schema = self._build_schema()

    def _build_schema(self) -> ToolSchema:
        """Generate ToolSchema from function signature and type hints."""
        sig = inspect.signature(self.func)
        hints = get_type_hints(self.func)
        parameters: list[ToolParameter] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            py_type = hints.get(param_name, str)
            json_type = _python_type_to_json(py_type)

            # Extract description from docstring (simple heuristic)
            param_desc = ""

            has_default = param.default is not inspect.Parameter.empty
            default = param.default if has_default else None

            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=json_type,
                    description=param_desc,
                    required=not has_default,
                    default=default,
                )
            )

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return the result as a string.

        Both sync and async functions are supported.
        """
        try:
            if self._is_async:
                result = await self.func(**kwargs)
            else:
                # Run sync functions in a thread to avoid blocking
                result = await asyncio.to_thread(self.func, **kwargs)
            return str(result)
        except Exception as e:
            return f"Error executing tool '{self.name}': {type(e).__name__}: {e}"

    async def __call__(self, **kwargs: Any) -> str:
        """Allow calling the tool directly: ``await my_tool(x=1)``."""
        return await self.execute(**kwargs)

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"


# ── @tool decorator ─────────────────────────────────────────────────


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Tool | Callable[..., Tool]:
    """Decorator to convert a function into a :class:`Tool`.

    Can be used with or without arguments::

        @tool
        def search(query: str) -> str: ...

        @tool(description="Search the web")
        def search(query: str) -> str: ...
    """
    def _wrap(fn: Callable[..., Any]) -> Tool:
        return Tool(fn, name=name, description=description)

    if func is not None:
        # Used as @tool without parentheses
        return _wrap(func)
    # Used as @tool(...) with arguments
    return _wrap
