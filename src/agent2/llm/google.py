"""Google Gemini LLM provider adapter."""

from __future__ import annotations

import uuid
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


class GoogleLLM(BaseLLM):
    """Adapter for Google's Gemini API (via ``google-genai``).

    Parameters
    ----------
    model : str
        Model name, e.g. ``"gemini-2.0-flash"``.
    api_key : str | None
        Google AI API key.
    """

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
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
                from google import genai
            except ImportError as e:
                raise ImportError(
                    "google-genai package is required. Install with: "
                    "uv pip install 'agent2[google]'"
                ) from e

            api_key = self._api_key
            if api_key is None:
                from agent2.utils.config import settings
                api_key = settings.google_api_key
            self._client = genai.Client(api_key=api_key)
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
        from google.genai import types

        # Build contents — Gemini uses a flat content list
        contents: list[Any] = []
        system_instruction: str | None = None

        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_instruction = msg.content
            elif msg.role == Role.USER:
                contents.append(types.Content(role="user", parts=[types.Part(text=msg.content or "")]))
            elif msg.role == Role.ASSISTANT:
                parts: list[Any] = []
                if msg.content:
                    parts.append(types.Part(text=msg.content))
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append(
                            types.Part(
                                function_call=types.FunctionCall(
                                    name=tc.name, args=tc.arguments
                                )
                            )
                        )
                contents.append(types.Content(role="model", parts=parts))
            elif msg.role == Role.TOOL and msg.tool_result:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name="tool",
                                    response={"result": msg.tool_result.content},
                                )
                            )
                        ],
                    )
                )

        # Build config
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )
        if system_instruction:
            config.system_instruction = system_instruction
        if tools:
            config.tools = [self._to_gemini_tool(tools)]

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        return self._from_gemini_response(response)

    # ── Format conversion ───────────────────────────────────────────

    @staticmethod
    def _to_gemini_tool(schemas: list[ToolSchema]) -> Any:
        """Convert list of ToolSchema into a Gemini Tool."""
        from google.genai import types

        declarations = []
        for schema in schemas:
            declarations.append(
                types.FunctionDeclaration(
                    name=schema.name,
                    description=schema.description,
                    parameters=schema.to_json_schema(),
                )
            )
        return types.Tool(function_declarations=declarations)

    @staticmethod
    def _from_gemini_response(response: Any) -> LLMResponse:
        """Convert Gemini response to internal LLMResponse."""
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.text:
                    content_parts.append(part.text)
                elif part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{uuid.uuid4().hex[:8]}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

        message = Message.assistant(
            content="\n".join(content_parts) if content_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        usage = Usage()
        if response.usage_metadata:
            um = response.usage_metadata
            usage = Usage(
                prompt_tokens=um.prompt_token_count or 0,
                completion_tokens=um.candidates_token_count or 0,
                total_tokens=um.total_token_count or 0,
            )

        return LLMResponse(message=message, usage=usage, raw_response=response)
