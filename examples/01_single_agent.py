"""Example 01: Single Agent — Basic ReAct pattern.

Demonstrates:
- Creating an LLM instance
- Creating a ReAct agent with tools
- Running a task and observing the Thought/Action/Observation loop

Usage:
    export AGENT2_OPENAI_API_KEY=sk-...
    uv run examples/01_single_agent.py
"""

import os
import asyncio

from agent2.llm import create_llm
from agent2.agent import ReActAgent
from agent2.tools.builtin import python_exec


async def main():
    # 1. Create an LLM — switch provider by changing the first argument
    #llm = create_llm("openai", model="gpt-4o-mini")
    #llm = create_llm("ollama", model="gemma4:e2b")
    llm = create_llm("deepseek")

    # 2. Create a ReAct agent with a code execution tool
    agent = ReActAgent(
        "CodeAssistant",
        llm=llm,
        system_prompt=(
            "You are a helpful coding assistant. You can execute Python code "
            "to verify your answers. Always show your reasoning."
        ),
        tools=[python_exec],
    )

    # 3. Run a task
    result = await agent.run(
        "What is the sum of the first 100 prime numbers? Use Python to calculate it."
    )

    print("\n" + "=" * 60)
    print("FINAL RESULT:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
