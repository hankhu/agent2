"""OpenAI LLM provider adapter."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

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
    """Adapter for OpenAI and OpenAI-compatible Chat Completions APIs.

    Parameters
    ----------
    model : str
        Model name, e.g. ``"gpt-4o-mini"``, ``"deepseek-chat"``.
    api_key : str | None
        API key. Falls back to ``AGENT2_API_KEY``.
    base_url : str | None
        Custom base URL (for DeepSeek, Ollama, vLLM, proxies, etc.).
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=provider,
            base_url=base_url,
            **kwargs,
        )
        self._api_key = api_key
        self._base_url = base_url
        self._client: Any = None  # lazy init

    @property
    def base_url(self) -> str | None:
        if self._base_url:
            return self._base_url
        try:
            from agent2.utils.config import settings as s
            return s.base_url
        except Exception:
            return None

    @base_url.setter
    def base_url(self, value: str | None) -> None:
        self._base_url = value

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as e:
                raise ImportError(
                    "openai package is required. Install with: uv add openai"
                ) from e

            kwargs: dict[str, Any] = {}
            api_key = self._api_key
            if api_key is None:
                from agent2.utils.config import settings
                api_key = settings.api_key
            if api_key:
                kwargs["api_key"] = api_key

            base_url = self._base_url
            if not base_url:
                from agent2.utils.config import settings as s
                base_url = s.base_url

            if base_url:
                base_url = base_url.strip()
                if not any(v in base_url for v in ("/v1", "/v2", "/v3", "/v4")) and not base_url.endswith("/openai"):
                    base_url = base_url.rstrip("/") + "/v1"
                kwargs["base_url"] = base_url

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
        oai_messages = [self._to_oai_message(m) for m in self._repair_tool_messages(messages)]

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
        llm_response = self._from_oai_response(response)
        self._record_usage(llm_response.usage)
        return llm_response

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()

        oai_messages = [self._to_oai_message(m) for m in self._repair_tool_messages(messages)]

        req: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            **kwargs,
        }

        if tools:
            req["tools"] = [self._to_oai_tool(t) for t in tools]

        collected_content: list[str] = []
        usage_received = False
        stream = await client.chat.completions.create(**req)
        async for chunk in stream:
            # Providers that honor stream_options={"include_usage": True} attach
            # usage to the final chunk; capture it when present so last_usage /
            # total_usage stay live for streamed requests too.
            if chunk.usage is not None:
                usage_received = True
                self._record_usage(
                    Usage(
                        prompt_tokens=chunk.usage.prompt_tokens or 0,
                        completion_tokens=chunk.usage.completion_tokens or 0,
                        total_tokens=chunk.usage.total_tokens or 0,
                    )
                )
            if chunk.choices and chunk.choices[0].delta.content:
                collected_content.append(chunk.choices[0].delta.content)
                yield chunk.choices[0].delta.content

        # Fallback: estimate usage when the provider didn't report it.
        if not usage_received:
            est_completion = sum(len(c) for c in collected_content) // 4 or 1
            est_prompt = sum(
                len(m.content or "") for m in messages
            ) // 4 or 1
            self._record_usage(
                Usage(
                    prompt_tokens=est_prompt,
                    completion_tokens=est_completion,
                    total_tokens=est_prompt + est_completion,
                )
            )

    # ── Format conversion ───────────────────────────────────────────

    @staticmethod
    def _repair_tool_messages(messages: list[Message]) -> list[Message]:
        """Return a copy with complete tool responses after tool_calls.

        OpenAI-compatible APIs reject assistant messages that contain
        ``tool_calls`` unless every ``tool_call_id`` is answered by a following
        ``tool`` message.  This guard repairs incomplete histories before they
        are sent to the API.
        """
        repaired = list(messages)
        i = 0
        while i < len(repaired):
            msg = repaired[i]
            if msg.role == Role.ASSISTANT and msg.tool_calls:
                expected = {tc.id for tc in msg.tool_calls}
                j = i + 1
                found: set[str] = set()
                while j < len(repaired) and repaired[j].role == Role.TOOL:
                    if repaired[j].tool_result is not None:
                        found.add(repaired[j].tool_result.tool_call_id)
                    j += 1
                missing = expected - found
                if missing:
                    insert_at = j
                    for tool_call_id in sorted(missing):
                        repaired.insert(
                            insert_at,
                            Message.tool(
                                tool_call_id,
                                "Tool execution did not return a result.",
                                is_error=True,
                            ),
                        )
                        insert_at += 1
                    i = insert_at
                    continue
                i = j
            else:
                i += 1
        return repaired

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
