"""Base class for multi-agent crews (orchestrators)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent2.agent.base import BaseAgent
from agent2.utils.logging import AgentLogger


class BaseCrew(ABC):
    """Abstract base for multi-agent orchestration.

    A Crew manages a group of agents working together to solve a task.
    Different subclasses implement different coordination patterns.

    Parameters
    ----------
    name : str
        Name of this crew.
    agents : list[BaseAgent]
        The agents in this crew.
    verbose : bool
        Enable detailed logging.
    """

    def __init__(
        self,
        name: str,
        *,
        agents: list[BaseAgent],
        verbose: bool = True,
    ) -> None:
        self.name = name
        self.agents = agents
        self.verbose = verbose
        self.log = AgentLogger(f"Crew:{name}", verbose=verbose)

    async def run(self, task: str) -> str:
        """Execute the crew on a task.

        Parameters
        ----------
        task : str
            The task to accomplish.

        Returns
        -------
        str
            The final result.
        """
        self.log.start(task)
        result = await self._orchestrate(task)
        self.log.finish(result)
        return result

    @abstractmethod
    async def _orchestrate(self, task: str) -> str:
        """Implement the coordination pattern. Subclasses override this."""
        ...

    def __repr__(self) -> str:
        agent_names = [a.name for a in self.agents]
        return f"{self.__class__.__name__}(name={self.name!r}, agents={agent_names})"
