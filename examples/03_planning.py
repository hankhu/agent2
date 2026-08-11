"""Example 03: Planning — Plan-and-Execute pattern.

Demonstrates:
- PlannerAgent that separates planning from execution
- Dynamic re-planning based on intermediate results
- Multi-step task decomposition

Usage:
    export AGENT2_OPENAI_API_KEY=sk-...
    uv run examples/03_planning.py
"""

import asyncio

from agent2.llm import create_llm
from agent2.agent import PlannerAgent
from agent2.tools.builtin import web_search, python_exec


async def main():
    llm = create_llm("deepseek")

    agent = PlannerAgent(
        "Researcher",
        llm=llm,
        tools=[web_search, python_exec],
        enable_replan=True,
        max_step_iterations=3,
    )

    result = await agent.run(
        "Compare the population of Tokyo, New York, and London. "
        "Which city is the most densely populated? "
        "Show the calculations."
    )

    print("\n" + "=" * 60)
    print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
