"""MCP (Model Context Protocol) client — connects to external tool servers.

Wraps MCP server tools as standard agent2 :class:`~agent2.tools.base.Tool`
instances so they are transparent to the agent layer.

Requires the optional ``mcp`` dependency::

    uv pip install agent2[mcp]

Configuration in ``~/.config/agent2/config.json``::

    {
      "mcp_servers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)


# ── Configuration ───────────────────────────────────────────────────


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str | None = Field(
        default=None,
        description="Executable for stdio transport",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Arguments for the command",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Extra environment variables",
    )
    url: str | None = Field(
        default=None,
        description="URL for SSE transport (mutually exclusive with command)",
    )


# ── MCP Tool wrapper ───────────────────────────────────────────────


def _make_mcp_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    call_fn: Any,
) -> Any:
    """Wrap an MCP tool as an agent2 Tool instance."""
    from agent2.llm.message import ToolParameter, ToolSchema
    from agent2.tools.base import Tool

    # Parse input_schema properties into ToolParameters
    properties = input_schema.get("properties", {})
    required_set = set(input_schema.get("required", []))
    parameters: list[ToolParameter] = []
    for param_name, param_info in properties.items():
        parameters.append(
            ToolParameter(
                name=param_name,
                type=param_info.get("type", "string"),
                description=param_info.get("description", ""),
                required=param_name in required_set,
                default=param_info.get("default"),
            )
        )

    schema = ToolSchema(name=name, description=description, parameters=parameters)

    # Build a Tool with a custom execute that calls the MCP server
    tool = Tool.__new__(Tool)
    tool.name = name
    tool.description = description
    tool.schema = schema
    tool.func = call_fn
    tool._is_async = True

    return tool


# ── Manager ─────────────────────────────────────────────────────────


class MCPManager:
    """Manages connections to one or more MCP servers.

    Usage::

        manager = MCPManager({"fs": MCPServerConfig(command="npx", args=[...])})
        tools = await manager.connect()
        # ... use tools ...
        await manager.close()
    """

    def __init__(self, servers: dict[str, MCPServerConfig]) -> None:
        self._server_configs = servers
        self._sessions: list[Any] = []
        self._cleanup_fns: list[Any] = []

    async def connect(self) -> list[Any]:
        """Connect to all configured MCP servers and return discovered tools.

        Returns
        -------
        list[Tool]
            Agent2 Tool instances wrapping MCP server tools.
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            _log.warning(
                "MCP package not installed. Install with: uv pip install agent2[mcp]"
            )
            return []

        all_tools: list[Any] = []

        for server_name, cfg in self._server_configs.items():
            try:
                tools = await self._connect_stdio(
                    server_name, cfg, ClientSession, StdioServerParameters, stdio_client,
                )
                all_tools.extend(tools)
                _log.info("MCP server '%s': discovered %d tools", server_name, len(tools))
            except Exception as exc:
                _log.warning("Failed to connect to MCP server '%s': %s", server_name, exc)

        return all_tools

    async def _connect_stdio(
        self,
        server_name: str,
        cfg: MCPServerConfig,
        ClientSession: type,
        StdioServerParameters: type,
        stdio_client: Any,
    ) -> list[Any]:
        """Connect to a single stdio-based MCP server."""
        if not cfg.command:
            _log.warning("MCP server '%s': no command specified, skipping", server_name)
            return []

        import os

        env = {**os.environ, **cfg.env} if cfg.env else None
        server_params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args,
            env=env,
        )

        # Use context manager protocol manually so we can hold the session open.
        # Wrap in try/except so already-opened resources are cleaned up on failure.
        transport_ctx = stdio_client(server_params)
        transport = await transport_ctx.__aenter__()
        try:
            self._cleanup_fns.append(transport_ctx.__aexit__)
            read_stream, write_stream = transport
            session_ctx = ClientSession(read_stream, write_stream)
            session = await session_ctx.__aenter__()
        except BaseException:
            await transport_ctx.__aexit__(None, None, None)
            raise
        self._cleanup_fns.append(session_ctx.__aexit__)
        self._sessions.append(session)

        await session.initialize()

        # Discover tools
        result = await session.list_tools()
        tools: list[Any] = []
        for mcp_tool in result.tools:
            async def _call(session=session, tool_name=mcp_tool.name, **kwargs: Any) -> str:
                resp = await session.call_tool(tool_name, arguments=kwargs)
                # MCP tool results are a list of content blocks
                parts = []
                for block in resp.content:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                return "\n".join(parts) if parts else ""

            tool = _make_mcp_tool(
                name=mcp_tool.name,
                description=mcp_tool.description or "",
                input_schema=mcp_tool.inputSchema if hasattr(mcp_tool, "inputSchema") else {},
                call_fn=_call,
            )
            tools.append(tool)

        return tools

    async def close(self) -> None:
        """Disconnect from all MCP servers."""
        for cleanup in reversed(self._cleanup_fns):
            try:
                await cleanup(None, None, None)
            except Exception:
                pass
        self._cleanup_fns.clear()
        self._sessions.clear()
