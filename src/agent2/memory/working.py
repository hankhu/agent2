"""Working Memory — short-term conversation history management.

Maintains the current conversation context with automatic summarisation
when the history grows too long.
"""

from __future__ import annotations

from typing import Any

from agent2.llm.message import Message, Role
from agent2.memory.base import BaseMemory, MemoryItem
from agent2.utils.config import settings


class WorkingMemory(BaseMemory):
    """Short-term memory based on conversation message history.

    Features:
    - Sliding window to limit context length
    - Automatic summarisation when messages exceed the limit
    - Keyword-based search over recent messages

    Parameters
    ----------
    max_messages : int
        Maximum messages to keep before triggering summarisation.
    """

    def __init__(self, max_messages: int | None = None) -> None:
        self.max_messages = max_messages or settings.memory_max_messages
        self._messages: list[Message] = []
        self._summaries: list[str] = []

    @property
    def messages(self) -> list[Message]:
        """Current conversation history."""
        return list(self._messages)

    @property
    def message_count(self) -> int:
        return len(self._messages)

    # ── BaseMemory interface ────────────────────────────────────────

    async def add(self, content: str, **metadata: Any) -> None:
        """Add a message to working memory."""
        role = metadata.get("role", "user")
        msg = Message(role=Role(role), content=content)
        self._messages.append(msg)

        # Check if we need to compress
        if len(self._messages) > self.max_messages:
            await self._compress()

    async def search(self, query: str, *, top_k: int = 5) -> list[MemoryItem]:
        """Search working memory by keyword matching.

        Uses simple keyword overlap for lightweight search.
        """
        query_words = set(query.lower().split())
        scored: list[MemoryItem] = []

        for msg in self._messages:
            if not msg.content:
                continue
            msg_words = set(msg.content.lower().split())
            overlap = len(query_words & msg_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                scored.append(
                    MemoryItem(
                        content=msg.content,
                        metadata={"role": msg.role.value},
                        score=score,
                    )
                )

        # Also include summaries
        for summary in self._summaries:
            summary_words = set(summary.lower().split())
            overlap = len(query_words & summary_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                scored.append(
                    MemoryItem(
                        content=summary,
                        metadata={"type": "summary"},
                        score=score,
                    )
                )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def clear(self) -> None:
        """Clear all working memory."""
        self._messages.clear()
        self._summaries.clear()

    # ── Message management ──────────────────────────────────────────

    def add_message(self, message: Message) -> None:
        """Add a Message object directly (convenience method)."""
        self._messages.append(message)

    def get_messages_for_llm(self, system_prompt: str | None = None) -> list[Message]:
        """Get the full message list ready for LLM consumption.

        Prepends summaries of compressed history and optional system prompt.
        """
        result: list[Message] = []

        if system_prompt:
            result.append(Message.system(system_prompt))

        # Add compressed history summaries
        if self._summaries:
            summary_text = (
                "Summary of earlier conversation:\n"
                + "\n".join(f"- {s}" for s in self._summaries)
            )
            result.append(Message.system(summary_text))

        result.extend(self._messages)
        return result

    async def _compress(self) -> None:
        """Compress old messages into a summary.

        Keeps the most recent messages and summarises the rest.
        This is a simple implementation — a production version would
        use the LLM to generate the summary.
        """
        keep_count = self.max_messages // 2
        old_messages = self._messages[:-keep_count]
        self._messages = self._messages[-keep_count:]

        # Simple extractive summary: keep the content of each message
        summary_parts: list[str] = []
        for msg in old_messages:
            if msg.content and msg.role in (Role.USER, Role.ASSISTANT):
                truncated = msg.content[:100] + "…" if len(msg.content) > 100 else msg.content
                summary_parts.append(f"[{msg.role.value}] {truncated}")

        if summary_parts:
            self._summaries.append(" | ".join(summary_parts))
