"""Example 02: Tool Use — defining and using custom tools.

Demonstrates:
- @tool decorator for creating tools from functions
- ToolRegistry for managing multiple tools
- Agent using tools to solve problems

Usage:
    export AGENT2_OPENAI_API_KEY=sk-...
    uv run examples/02_tool_use.py
"""

import asyncio
import math

from agent2.llm import create_llm
from agent2.agent import ReActAgent
from agent2.tools import tool, ToolRegistry


# ── Define custom tools ─────────────────────────────────────────────


@tool(description="Calculate basic math expressions. Supports +, -, *, /, **, sqrt.")
def calculator(expression: str) -> str:
    """Evaluate a math expression safely."""
    allowed = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pi": math.pi,
        "e": math.e,
        "abs": abs,
        "round": round,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


@tool(description="Get the current date and time.")
def get_current_time() -> str:
    """Return the current date and time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool(description="Convert temperature between Celsius and Fahrenheit.")
def convert_temperature(value: float, from_unit: str) -> str:
    """Convert temperature. from_unit should be 'C' or 'F'."""
    if from_unit.upper() == "C":
        result = value * 9 / 5 + 32
        return f"{value}°C = {result:.1f}°F"
    elif from_unit.upper() == "F":
        result = (value - 32) * 5 / 9
        return f"{value}°F = {result:.1f}°C"
    else:
        return f"Unknown unit: {from_unit}. Use 'C' or 'F'."


# ── Main ────────────────────────────────────────────────────────────


async def main():
    llm = create_llm("openai", model="deepseek-v4-flash")

    # Create agent with multiple custom tools
    agent = ReActAgent(
        "ToolDemo",
        llm=llm,
        tools=[calculator, get_current_time, convert_temperature],
    )

    # Test with a task requiring multiple tools
    result = await agent.run(
        "What is the current time? Also, what is 37°C in Fahrenheit? "
        "And what is the square root of 144?"
    )

    print("\n" + "=" * 60)
    print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
