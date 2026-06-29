"""Example 05: Multi-Agent — crew orchestration patterns.

Demonstrates:
- SequentialCrew: pipeline-style execution
- SupervisorCrew: supervisor delegates to workers
- DebateCrew: agents debate and reach consensus

Usage:
    export AGENT2_OPENAI_API_KEY=sk-...
    uv run examples/05_multi_agent.py
"""

import asyncio

from agent2.llm import create_llm
from agent2.agent import ReActAgent
from agent2.crew import SequentialCrew, SupervisorCrew, DebateCrew


async def demo_sequential():
    """Sequential pipeline: Research → Write → Edit."""
    print("\n" + "=" * 60)
    print("Sequential Crew Demo")
    print("=" * 60)

    llm = create_llm("openai", model="deepseek-v4-flash")

    researcher = ReActAgent(
        "researcher",
        llm=llm,
        system_prompt="You are a research expert. Gather key facts and data points.",
    )
    writer = ReActAgent(
        "writer",
        llm=llm,
        system_prompt="You are a professional writer. Create clear, engaging content from research.",
    )
    editor = ReActAgent(
        "editor",
        llm=llm,
        system_prompt="You are an editor. Polish the writing for clarity and accuracy.",
    )
    translator = ReActAgent(
        "translator",
        llm=llm,
        system_prompt="You are an translator. Translate the writing into Chinese.",
    )

    crew = SequentialCrew("content_pipeline", agents=[researcher, writer, editor, translator])
    result = await crew.run("Write a brief explanation of how neural networks work")
    print(f"\nFinal output:\n{result}")


async def demo_supervisor():
    """Supervisor delegates to specialized workers."""
    print("\n" + "=" * 60)
    print("Supervisor Crew Demo")
    print("=" * 60)

    llm = create_llm("openai", model="gpt-4o-mini")

    analyst = ReActAgent(
        "analyst",
        llm=llm,
        system_prompt="You are a data analyst. Focus on numbers, trends, and insights.",
    )
    strategist = ReActAgent(
        "strategist",
        llm=llm,
        system_prompt="You are a strategy consultant. Focus on actionable recommendations.",
    )

    crew = SupervisorCrew(
        "consulting_team",
        agents=[analyst, strategist],
        supervisor_llm=llm,
    )
    result = await crew.run("What should a startup focus on in its first year?")
    print(f"\nFinal output:\n{result}")


async def demo_debate():
    """Agents with different perspectives debate."""
    print("\n" + "=" * 60)
    print("Debate Crew Demo")
    print("=" * 60)

    llm = create_llm("openai", model="gpt-4o-mini")

    optimist = ReActAgent(
        "optimist",
        llm=llm,
        system_prompt=(
            "You are an optimistic technology enthusiast. "
            "You focus on opportunities, benefits, and positive outcomes."
        ),
    )
    critic = ReActAgent(
        "critic",
        llm=llm,
        system_prompt=(
            "You are a critical thinker and devil's advocate. "
            "You focus on risks, limitations, and potential problems."
        ),
    )

    crew = DebateCrew(
        "tech_debate",
        agents=[optimist, critic],
        synthesizer_llm=llm,
        rounds=1,
    )
    result = await crew.run("Should companies fully adopt AI for customer service?")
    print(f"\nFinal output:\n{result}")


async def main():
    # Run one demo at a time to keep output readable
    # Uncomment the one you want to try:

    await demo_sequential()
    # await demo_supervisor()
    # await demo_debate()


if __name__ == "__main__":
    asyncio.run(main())
