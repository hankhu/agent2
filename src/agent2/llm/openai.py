"""OpenAI LLM provider adapter."""

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


class OpenAILLM(BaseLLM):
    """Adapter for OpenAI's Chat Completions API.

    Parameters
    ----------
    model : str
        Model name, e.g. ``"gpt-4o-mini"``, ``"gpt-4o"``.
    api_key : str | None
        API key. Falls back to ``AGENT2_OPENAI_API_KEY`` or ``OPENAI_API_KEY``.
    base_url : str | None
        Custom base URL (for Azure, proxies, etc.).
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature=temperature, max_tokens=max_tokens, **kwargs)
        self._api_key = api_key
        self._base_url = base_url
        self._client: Any = None  # lazy init

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as e:
                raise ImportError(
                    "openai package is required. Install with: "
                    "uv pip install 'agent2[openai]'"
                ) from e

            kwargs: dict[str, Any] = {}
            api_key = self._api_key
            if api_key is None:
                from agent2.utils.config import settings
                api_key = settings.openai_api_key
            if api_key:
                kwargs["api_key"] = api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            elif (from_settings := None) is None:
                from agent2.utils.config import settings as s
                if s.openai_base_url:
                    kwargs["base_url"] = s.openai_base_url

            self._client = AsyncOpenAI(**kwargs)
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

        # Convert messages to OpenAI format
        oai_messages = [self._to_oai_message(m) for m in messages]

        # Build request kwargs
        req: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **kwargs,
        }

        # Add tools if provided
        if tools:
            req["tools"] = [self._to_oai_tool(t) for t in tools]

        response = await client.chat.completions.create(**req)
        return self._from_oai_response(response)

    # ── Format conversion ───────────────────────────────────────────

    @staticmethod
    def _to_oai_message(msg: Message) -> dict[str, Any]:
        """Convert internal Message to OpenAI message dict."""
        if msg.role == Role.TOOL and msg.tool_result:
            return {
                "role": "tool",
                "tool_call_id": msg.tool_result.tool_call_id,
                "content": msg.tool_result.content,
            }

        result: dict[str, Any] = {"role": msg.role.value}
        if msg.content is not None:
            result["content"] = msg.content

        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in msg.tool_calls
            ]
        return result

    @staticmethod
    def _to_oai_tool(schema: ToolSchema) -> dict[str, Any]:
        """Convert ToolSchema to OpenAI function tool format."""
        return {
            "type": "function",
            "function": {
                "name": schema.name,
                "description": schema.description,
                "parameters": schema.to_json_schema(),
            },
        }

    @staticmethod
    def _from_oai_response(response: Any) -> LLMResponse:
        """Convert OpenAI response to internal LLMResponse."""
        choice = response.choices[0]
        oai_msg = choice.message

        # Parse tool calls
        tool_calls: list[ToolCall] | None = None
        if oai_msg.tool_calls:
            tool_calls = []
            for tc in oai_msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        message = Message.assistant(
            content=oai_msg.content,
            tool_calls=tool_calls,
        )

        usage = Usage()
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return LLMResponse(message=message, usage=usage, raw_response=response)
