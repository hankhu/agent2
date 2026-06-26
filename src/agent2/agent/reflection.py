"""Reflection mixin — self-critique and iterative refinement.

Adds a reflection capability that lets an agent evaluate its own output
and retry if quality is insufficient. Can be mixed into any agent type.
"""

from __future__ import annotations

from typing import Any

from agent2.llm.base import BaseLLM
from agent2.llm.message import Message
from agent2.utils.logging import AgentLogger


_REFLECTION_PROMPT = """You are a critical reviewer. Evaluate the following response to the given task.

Task: {task}
Response: {response}

Evaluate the response on these criteria:
1. **Correctness**: Is the information accurate?
2. **Completeness**: Does it fully address the task?
3. **Clarity**: Is it well-structured and easy to understand?

Respond in this exact JSON format:
{{
    "score": <1-10>,
    "passed": <true if score >= 7, false otherwise>,
    "feedback": "<specific suggestions for improvement>"
}}
"""


class ReflectionMixin:
    """Mixin that adds self-reflection capability to any agent.

    After the agent produces an answer, it evaluates the answer and
    retries with the feedback if the quality is below threshold.

    Usage::

        class MyReflectiveAgent(ReflectionMixin, ReActAgent):
            pass

        agent = MyReflectiveAgent("reflector", llm=llm, max_reflections=2)
    """

    max_reflections: int = 2
    reflection_threshold: int = 7  # Minimum score (1-10) to pass

    async def run(self, task: str) -> str:
        """Override run() to add reflection loop."""
        # Get the base agent's run result
        result = await super().run(task)  # type: ignore[misc]

        # Access the logger from the base agent
        log: AgentLogger = getattr(self, "log", AgentLogger("reflection"))
        llm: BaseLLM = getattr(self, "llm")

        for attempt in range(self.max_reflections):
            evaluation = await self._reflect(llm, task, result)

            if evaluation.get("passed", True):
                return result

            feedback = evaluation.get("feedback", "Try to improve your response.")
            score = evaluation.get("score", "?")
            log.thought(
                f"Reflection {attempt + 1}/{self.max_reflections}: "
                f"Score {score}/10 — {feedback}"
            )

            # Retry with feedback
            result = await self._retry_with_feedback(llm, task, result, feedback)
            log.final_answer(result)

        return result

    @staticmethod
    async def _reflect(
        llm: BaseLLM, task: str, response: str
    ) -> dict[str, Any]:
        """Ask the LLM to evaluate a response."""
        import json

        prompt = _REFLECTION_PROMPT.format(task=task, response=response)
        llm_response = await llm.chat([
            Message.system("You are a critical reviewer. Respond in JSON only."),
            Message.user(prompt),
        ])

        content = llm_response.content or ""
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            # If parsing fails, assume it passed
            return {"score": 10, "passed": True, "feedback": ""}

    @staticmethod
    async def _retry_with_feedback(
        llm: BaseLLM, task: str, previous: str, feedback: str
    ) -> str:
        """Generate an improved response incorporating feedback."""
        response = await llm.chat([
            Message.system(
                "You previously answered a task but your answer needs improvement. "
                "Generate an improved response based on the feedback."
            ),
            Message.user(
                f"Original task: {task}\n\n"
                f"Your previous answer:\n{previous}\n\n"
                f"Reviewer feedback:\n{feedback}\n\n"
                f"Please provide an improved answer."
            ),
        ])
        return response.content or previous
