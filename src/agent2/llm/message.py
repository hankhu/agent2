"""Unified message data models for LLM communication.

These models normalise the different message formats used by OpenAI,
Anthropic, Google, and Ollama into a single representation that the
rest of the framework consumes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────────


class Role(str, Enum):
    """Message role in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ── Tool-related models ────────────────────────────────────────────


class ToolCall(BaseModel):
    """A request from the LLM to invoke a tool."""

    id: str = Field(description="Unique identifier for this tool call")
    name: str = Field(description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Parsed arguments for the tool",
    )


class ToolResult(BaseModel):
    """The result of executing a tool, sent back to the LLM."""

    tool_call_id: str = Field(description="ID of the ToolCall this responds to")
    content: str = Field(description="Textual result of the tool execution")
    is_error: bool = Field(default=False, description="Whether the execution failed")


# ── Messages ────────────────────────────────────────────────────────


class Message(BaseModel):
    """A single message in a conversation.

    For regular messages, *content* carries the text.
    For assistant messages that invoke tools, *tool_calls* is populated.
    For tool-result messages, *tool_result* is populated.
    """

    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_result: ToolResult | None = None

    # Convenience constructors ───────────────────────────────────────

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(
        cls,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
    ) -> Message:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, tool_call_id: str, content: str, *, is_error: bool = False) -> Message:
        return cls(
            role=Role.TOOL,
            tool_result=ToolResult(
                tool_call_id=tool_call_id, content=content, is_error=is_error
            ),
        )


# ── Tool Schema (for sending to LLM) ───────────────────────────────


class ToolParameter(BaseModel):
    """Describes a single parameter of a tool."""

    name: str
    type: str  # JSON Schema type: string, integer, number, boolean, array, object
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


class ToolSchema(BaseModel):
    """Schema describing a tool for the LLM.

    This is the framework's internal representation; each LLM adapter
    converts it to the provider-specific format.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to standard JSON Schema (used by OpenAI-compatible APIs)."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type}
            if p.description:
                prop["description"] = p.description
            if p.enum is not None:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema


# ── LLM Response ────────────────────────────────────────────────────


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """Normalised response from any LLM provider."""

    message: Message
    usage: Usage = Field(default_factory=Usage)
    raw_response: Any = Field(
        default=None,
        description="Original provider-specific response object",
        exclude=True,
    )

    @property
    def content(self) -> str | None:
        return self.message.content

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls or []

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.message.tool_calls)
