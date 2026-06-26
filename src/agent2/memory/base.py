"""Abstract base class for memory systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """A single item stored in memory."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(default=0.0, description="Relevance score (for search results)")


class BaseMemory(ABC):
    """Abstract base for all memory implementations.

    Subclasses must implement add(), search(), and clear().
    """

    @abstractmethod
    async def add(self, content: str, **metadata: Any) -> None:
        """Store a piece of information in memory.

        Parameters
        ----------
        content : str
            The text content to remember.
        **metadata
            Additional metadata (e.g., source, timestamp).
        """
        ...

    @abstractmethod
    async def search(self, query: str, *, top_k: int = 5) -> list[MemoryItem]:
        """Retrieve relevant memories for a given query.

        Parameters
        ----------
        query : str
            The search query.
        top_k : int
            Maximum number of results to return.

        Returns
        -------
        list[MemoryItem]
            Relevant memories, sorted by relevance (highest first).
        """
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Remove all items from memory."""
        ...

    async def get_context(self, query: str, *, top_k: int = 5) -> str:
        """Retrieve memories formatted as context for injection into a prompt.

        Returns
        -------
        str
            Formatted context string, or empty string if no relevant memories.
        """
        items = await self.search(query, top_k=top_k)
        if not items:
            return ""

        lines = ["Relevant context from memory:"]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.content}")
        return "\n".join(lines)
