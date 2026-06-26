"""Sequential Crew — agents work in a pipeline.

Each agent receives the output of the previous agent as context.
Useful for workflows like: Research → Write → Edit → Review.
"""

from __future__ import annotations

from agent2.crew.base import BaseCrew


class SequentialCrew(BaseCrew):
    """Pipeline-style multi-agent orchestration.

    Agents are executed in order. Each agent receives the original task
    plus the accumulated outputs of all previous agents.

    Usage::

        researcher = ReActAgent("researcher", llm=llm, tools=[web_search])
        writer = ReActAgent("writer", llm=llm)
        editor = ReActAgent("editor", llm=llm)

        crew = SequentialCrew("content_team", agents=[researcher, writer, editor])
        result = await crew.run("Write an article about quantum computing")
    """

    async def _orchestrate(self, task: str) -> str:
        """Execute agents sequentially, passing results forward."""
        accumulated_context: list[dict[str, str]] = []

        for i, agent in enumerate(self.agents):
            self.log.delegate(self.name, agent.name, f"Step {i + 1}")

            # Build the agent's input with context from previous steps
            if accumulated_context:
                context_text = "\n\n".join(
                    f"=== Output from {ctx['agent']} ===\n{ctx['result']}"
                    for ctx in accumulated_context
                )
                agent_input = (
                    f"Original task: {task}\n\n"
                    f"Previous steps:\n{context_text}\n\n"
                    f"Your turn. Continue working on this task based on the above context."
                )
            else:
                agent_input = task

            result = await agent.run(agent_input)
            accumulated_context.append({"agent": agent.name, "result": result})
            self.log.agent_message(agent.name, result)

        # Return the last agent's output
        return accumulated_context[-1]["result"] if accumulated_context else ""
