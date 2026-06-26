"""Crew module — multi-agent orchestration patterns.

- :class:`SequentialCrew` — Pipeline execution
- :class:`SupervisorCrew` — Supervisor delegates to workers
- :class:`DebateCrew` — Debate and consensus
"""

from agent2.crew.base import BaseCrew
from agent2.crew.sequential import SequentialCrew
from agent2.crew.supervisor import SupervisorCrew
from agent2.crew.debate import DebateCrew

__all__ = ["BaseCrew", "SequentialCrew", "SupervisorCrew", "DebateCrew"]
