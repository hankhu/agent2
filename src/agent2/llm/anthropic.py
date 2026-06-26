"""Anthropic (Claude) LLM provider adapter."""

from __future__ import annotations

import json
from typing import Any

from agent2.llm.base import BaseLLM
from agent2.llm.message import (
    LLMResponse,
    Message,
    Role,
    ToolCall,
    ToolSchema,
    Usage,
)


class AnthropicLLM(BaseLLM):
    """Adapter for Anthropic's Messages API.

    Parameters
    ----------
    model : str
        Model name, e.g. ``"claude-sonnet-4-20250514"``.
    api_key : str | None
        Anthropic API key.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        *,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature=temperature, max_tokens=max_tokens, **kwargs)
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as e:
                raise ImportError(
                    "anthropic package is required. Install with: "
                    "uv pip install 'agent2[anthropic]'"
                ) from e

            api_key = self._api_key
            if api_key is None:
                from agent2.utils.config import settings
                api_key = settings.anthropic_api_key
            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    # ── Chat ────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()

        # Anthropic separates system prompt from messages
        system_prompt: str | None = None
        conversation: list[Message] = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_prompt = msg.content
            else:
                conversation.append(msg)

        # Convert messages
        ant_messages = [self._to_ant_message(m) for m in conversation]

        # Build request
        req: dict[str, Any] = {
            "model": self.model,
            "messages": ant_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **kwargs,
        }
        if system_prompt:
            req["system"] = system_prompt
        if tools:
            req["tools"] = [self._to_ant_tool(t) for t in tools]

        response = await client.messages.create(**req)
        return self._from_ant_response(response)

    # ── Format conversion ───────────────────────────────────────────

    @staticmethod
    def _to_ant_message(msg: Message) -> dict[str, Any]:
        """Convert internal Message to Anthropic message dict."""
        if msg.role == Role.TOOL and msg.tool_result:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_result.tool_call_id,
                        "content": msg.tool_result.content,
                        "is_error": msg.tool_result.is_error,
                    }
                ],
            }

        if msg.role == Role.ASSISTANT:
            content_blocks: list[dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
            return {"role": "assistant", "content": content_blocks}

        return {"role": msg.role.value, "content": msg.content or ""}

    @staticmethod
    def _to_ant_tool(schema: ToolSchema) -> dict[str, Any]:
        """Convert ToolSchema to Anthropic tool format."""
        return {
            "name": schema.name,
            "description": schema.description,
            "input_schema": schema.to_json_schema(),
        }

    @staticmethod
    def _from_ant_response(response: Any) -> LLMResponse:
        """Convert Anthropic response to internal LLMResponse."""
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        message = Message.assistant(
            content="\n".join(content_parts) if content_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        usage = Usage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        return LLMResponse(message=message, usage=usage, raw_response=response)
