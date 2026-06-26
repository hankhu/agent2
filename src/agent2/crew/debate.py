"""Debate Crew — agents debate and critique each other.

Multiple agents provide perspectives on the same task, then engage
in rounds of critique and refinement to reach a consensus.
Useful for tasks requiring diverse viewpoints or high accuracy.
"""

from __future__ import annotations

from typing import Any

from agent2.agent.base import BaseAgent
from agent2.crew.base import BaseCrew
from agent2.llm.base import BaseLLM
from agent2.llm.message import Message


class DebateCrew(BaseCrew):
    """Multi-agent debate and consensus orchestration.

    All agents independently respond to the task, then engage in
    rounds of mutual critique. A final synthesis produces the answer.

    Parameters
    ----------
    name : str
        Crew name.
    agents : list[BaseAgent]
        Debating agents (typically 2-4).
    synthesizer_llm : BaseLLM
        LLM for the final synthesis (can be any of the agents' LLMs).
    rounds : int
        Number of debate rounds.

    Usage::

        optimist = ReActAgent("optimist", llm=llm, system_prompt="You tend to see opportunities...")
        pessimist = ReActAgent("pessimist", llm=llm, system_prompt="You focus on risks...")

        crew = DebateCrew("analysis", agents=[optimist, pessimist], synthesizer_llm=llm)
        result = await crew.run("Should we adopt microservices architecture?")
    """

    def __init__(
        self,
        name: str,
        *,
        agents: list[BaseAgent],
        synthesizer_llm: BaseLLM,
        rounds: int = 2,
        verbose: bool = True,
    ) -> None:
        super().__init__(name, agents=agents, verbose=verbose)
        self.synthesizer_llm = synthesizer_llm
        self.rounds = rounds

    async def _orchestrate(self, task: str) -> str:
        """Run the debate: initial responses → critique rounds → synthesis."""
        # Phase 1: Initial responses
        self.log.thought("Phase 1: Gathering initial perspectives")
        responses: dict[str, str] = {}
        for agent in self.agents:
            self.log.delegate(self.name, agent.name, "Initial response")
            result = await agent.run(task)
            responses[agent.name] = result
            self.log.agent_message(agent.name, result)

        # Phase 2: Debate rounds
        for round_num in range(1, self.rounds + 1):
            self.log.thought(f"Phase 2: Debate round {round_num}/{self.rounds}")
            new_responses: dict[str, str] = {}

            for agent in self.agents:
                # Show this agent what others said
                others_views = "\n\n".join(
                    f"=== {name}'s view ===\n{resp}"
                    for name, resp in responses.items()
                    if name != agent.name
                )

                critique_prompt = (
                    f"Original task: {task}\n\n"
                    f"Your previous response:\n{responses[agent.name]}\n\n"
                    f"Other perspectives:\n{others_views}\n\n"
                    f"Consider the other perspectives. Critique them where appropriate, "
                    f"acknowledge valid points, and provide your updated, refined response."
                )

                self.log.delegate(self.name, agent.name, f"Round {round_num} critique")
                result = await agent.run(critique_prompt)
                new_responses[agent.name] = result
                self.log.agent_message(agent.name, result)

            responses = new_responses

        # Phase 3: Synthesis
        self.log.thought("Phase 3: Synthesising consensus")
        return await self._synthesise(task, responses)

    async def _synthesise(self, task: str, responses: dict[str, str]) -> str:
        """Synthesise all perspectives into a final answer."""
        perspectives = "\n\n".join(
            f"=== {name}'s final perspective ===\n{resp}"
            for name, resp in responses.items()
        )

        response = await self.synthesizer_llm.chat([
            Message.system(
                "You are a synthesis agent. Multiple experts have debated a topic. "
                "Synthesise their perspectives into a balanced, comprehensive final answer. "
                "Highlight areas of consensus and note remaining disagreements."
            ),
            Message.user(
                f"Task: {task}\n\n"
                f"Expert perspectives after debate:\n{perspectives}\n\n"
                f"Provide a synthesised final answer."
            ),
        ])

        answer = response.content or ""
        self.log.final_answer(answer)
        return answer
