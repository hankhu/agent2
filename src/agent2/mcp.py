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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_log = logging.getLogger(__name__)


# ── Configuration ───────────────────────────────────────────────────


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["sse", "stdio", "http", "streamable_http"] = Field(
        default="sse",
        description="Transport type: 'sse' (default), 'http' / 'streamable_http', or 'stdio'",
    )
    url: str | None = Field(
        default=None,
        description="URL for HTTP or SSE transport",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional headers for HTTP or SSE transport (e.g. Authorization)",
    )
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
    disabled: bool = Field(
        default=False,
        description="Whether this MCP server is disabled",
    )
    always_allow: list[str] = Field(
        default_factory=list,
        alias="alwaysAllow",
        description="List of tool names that skip user confirmation",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "type" not in d:
            if "command" in d and "url" not in d:
                d["type"] = "stdio"
            else:
                d["type"] = "sse"
        elif d["type"] in ("streamable_http", "streamable-http"):
            d["type"] = "http"
        return d


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
        self._server_sessions: dict[str, Any] = {}
        self._server_cleanups: dict[str, list[Any]] = {}  # legacy, kept for compat
        self._server_tools: dict[str, list[Any]] = {}
        self._server_loops: dict[str, Any] = {}
        self._server_tasks: dict[str, asyncio.Task[None]] = {}
        self._server_shutdowns: dict[str, asyncio.Event] = {}
        self.always_allow_tools: set[str] = set()

    @property
    def servers(self) -> dict[str, MCPServerConfig]:
        """Mapping of server name to MCPServerConfig."""
        return self._server_configs

    @property
    def _sessions(self) -> list[Any]:
        return list(self._server_sessions.values())

    @property
    def _cleanup_fns(self) -> list[Any]:
        fns: list[Any] = []
        for cl in self._server_cleanups.values():
            fns.extend(cl)
        return fns

    def is_server_connected(self, server_name: str) -> bool:
        """Return True if server is currently connected with an active session on current loop."""
        if server_name not in self._server_sessions:
            return False
        loop = self._server_loops.get(server_name)
        if loop is not None and loop.is_closed():
            return False
        try:
            import asyncio

            running = asyncio.get_running_loop()
            if loop is not None and running != loop:
                return False
        except RuntimeError:
            pass
        return True

    def get_server_tools(self, server_name: str) -> list[Any]:
        """Return list of Tool instances registered for a server."""
        return list(self._server_tools.get(server_name, []))

    async def connect(self) -> list[Any]:
        """Connect to all configured MCP servers and return discovered tools.

        Returns
        -------
        list[Tool]
            Agent2 Tool instances wrapping MCP server tools.
        """
        all_tools: list[Any] = []
        self.always_allow_tools.clear()

        for server_name, cfg in self._server_configs.items():
            if cfg.disabled:
                _log.info("MCP server '%s': disabled, skipping", server_name)
                continue

            try:
                tools = await self.connect_server(server_name)
                all_tools.extend(tools)
            except BaseException as exc:
                _log.warning("Failed to connect to MCP server '%s': %s", server_name, exc)

        return all_tools

    async def connect_server(self, server_name: str) -> list[Any]:
        """Connect to a single MCP server and return discovered tools."""
        cfg = self._server_configs.get(server_name)
        if cfg is None:
            _log.warning("MCP server '%s': not found in configs", server_name)
            return []
        if cfg.disabled:
            _log.info("MCP server '%s': disabled, skipping", server_name)
            return []

        if server_name in self._server_sessions:
            await self.disconnect_server(server_name)

        try:
            import asyncio

            self._server_loops[server_name] = asyncio.get_running_loop()
        except RuntimeError:
            pass

        try:
            from mcp import ClientSession  # type: ignore[import-not-found]
        except ImportError:
            _log.warning(
                "MCP package not installed. Install with: uv pip install agent2[mcp]"
            )
            return []

        tools: list[Any] = []
        if cfg.type == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client  # type: ignore[import-not-found]

            tools = await self._connect_stdio(
                server_name, cfg, ClientSession, StdioServerParameters, stdio_client,
            )
        elif cfg.type == "sse":
            from mcp.client.sse import sse_client  # type: ignore[import-not-found]

            try:
                tools = await self._connect_sse(
                    server_name, cfg, ClientSession, sse_client,
                )
            except Exception as sse_err:
                try:
                    from mcp.client.streamable_http import (  # type: ignore[import-not-found]
                        create_mcp_http_client,
                        streamable_http_client,
                    )

                    _log.info(
                        "MCP server '%s': SSE connection failed (%s), attempting HTTP fallback...",
                        server_name,
                        sse_err,
                    )
                    tools = await self._connect_http(
                        server_name, cfg, ClientSession, streamable_http_client, create_mcp_http_client,
                    )
                except Exception:
                    raise sse_err
        elif cfg.type in ("http", "streamable_http"):
            from mcp.client.streamable_http import (  # type: ignore[import-not-found]
                create_mcp_http_client,
                streamable_http_client,
            )

            tools = await self._connect_http(
                server_name, cfg, ClientSession, streamable_http_client, create_mcp_http_client,
            )
        else:
            _log.warning(
                "MCP server '%s': unsupported type '%s', skipping",
                server_name,
                cfg.type,
            )
            return []

        self._server_tools[server_name] = tools
        if cfg.always_allow:
            if "*" in cfg.always_allow:
                self.always_allow_tools.update(t.name for t in tools)
            else:
                self.always_allow_tools.update(cfg.always_allow)

        _log.info("MCP server '%s': discovered %d tools", server_name, len(tools))
        return tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Invoke an MCP tool with loop-aware connection check and auto-retry."""
        if not self.is_server_connected(server_name):
            _log.info("MCP server '%s': reconnecting on current event loop", server_name)
            await self.connect_server(server_name)

        session = self._server_sessions.get(server_name)
        if session is None:
            return f"Error executing tool '{tool_name}': MCP server '{server_name}' is not connected."

        try:
            resp = await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:
            if "closed" in str(exc).lower():
                _log.warning(
                    "MCP server '%s' connection lost (%s), reconnecting...", server_name, exc
                )
                await self.connect_server(server_name)
                session = self._server_sessions.get(server_name)
                if session is None:
                    return f"Error executing tool '{tool_name}': failed to reconnect MCP server '{server_name}'."
                resp = await session.call_tool(tool_name, arguments=arguments)
            else:
                raise

        parts = []
        for block in resp.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) if parts else ""

    async def disconnect_server(
        self, server_name: str, keep_tools: bool = False
    ) -> list[str]:
        """Disconnect a single server and return the names of removed tools."""
        self._server_loops.pop(server_name, None)
        self._server_cleanups.pop(server_name, None)  # legacy
        self._server_sessions.pop(server_name, None)

        shutdown = self._server_shutdowns.pop(server_name, None)
        task = self._server_tasks.pop(server_name, None)

        if shutdown is not None:
            shutdown.set()
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as exc:
                _log.warning("MCP cleanup error for '%s': %s", server_name, exc)
                task.cancel()

        if keep_tools:
            tools = self._server_tools.get(server_name, [])
        else:
            tools = self._server_tools.pop(server_name, [])
        tool_names = [t.name for t in tools]

        if not keep_tools:
            for t_name in tool_names:
                self.always_allow_tools.discard(t_name)

            cfg = self._server_configs.get(server_name)
            if cfg and cfg.always_allow:
                for a_name in cfg.always_allow:
                    if not any(
                        a_name in (other_cfg.always_allow or [])
                        for s, other_cfg in self._server_configs.items()
                        if s != server_name and not other_cfg.disabled
                    ):
                        self.always_allow_tools.discard(a_name)

        return tool_names

    async def _discover_tools(self, server_name: str, session: Any) -> list[Any]:
        """Initialize session and discover all tools exposed by the MCP server."""
        await session.initialize()
        result = await session.list_tools()
        tools: list[Any] = []
        for mcp_tool in result.tools:
            async def _call(
                s_name: str = server_name, t_name: str = mcp_tool.name, **kwargs: Any
            ) -> str:
                return await self.call_tool(s_name, t_name, kwargs)

            input_schema = (
                getattr(mcp_tool, "input_schema", None)
                or getattr(mcp_tool, "inputSchema", None)
                or {}
            )
            if hasattr(input_schema, "model_dump"):
                input_schema = input_schema.model_dump()
            tool = _make_mcp_tool(
                name=mcp_tool.name,
                description=mcp_tool.description or "",
                input_schema=input_schema,
                call_fn=_call,
            )
            tools.append(tool)
        return tools

    async def _start_server_task(
        self,
        server_name: str,
        transport_ctx: Any,
        ClientSession: type,
    ) -> list[Any]:
        """Spawn a background task that holds the transport + session open.

        The task uses an ``asyncio.Queue`` to hand the live session back to the
        caller once both context managers have been entered, then blocks on a
        shutdown ``asyncio.Event``.  This ensures that ``__aexit__`` is always
        called from the *same* task as ``__aenter__``, which is required by
        anyio cancel scopes.
        """
        ready: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=1)
        shutdown: asyncio.Event = asyncio.Event()

        async def _task() -> None:
            try:
                async with transport_ctx as transport:
                    read_stream, write_stream = transport
                    async with ClientSession(read_stream, write_stream) as session:
                        ready.put_nowait(("ok", session))
                        await shutdown.wait()
            except BaseException as exc:
                try:
                    ready.put_nowait(("err", exc))
                except asyncio.QueueFull:
                    pass

        task: asyncio.Task[None] = asyncio.create_task(
            _task(), name=f"mcp-{server_name}"
        )
        kind, value = await ready.get()
        if kind == "err":
            # Let the task finish its (failed) cleanup before propagating.
            with __import__("contextlib").suppress(Exception):
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            raise value  # type: ignore[misc]

        session = value
        self._server_sessions[server_name] = session
        self._server_tasks[server_name] = task
        self._server_shutdowns[server_name] = shutdown
        try:
            self._server_loops[server_name] = asyncio.get_running_loop()
        except RuntimeError:
            pass
        return await self._discover_tools(server_name, session)

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
        return await self._start_server_task(
            server_name, stdio_client(server_params), ClientSession
        )

    async def _connect_sse(
        self,
        server_name: str,
        cfg: MCPServerConfig,
        ClientSession: type,
        sse_client: Any,
    ) -> list[Any]:
        """Connect to a single SSE-based MCP server."""
        if not cfg.url:
            _log.warning("MCP server '%s': no url specified for sse type, skipping", server_name)
            return []

        transport_ctx = sse_client(cfg.url, headers=cfg.headers or None)
        return await self._start_server_task(server_name, transport_ctx, ClientSession)

    async def _connect_http(
        self,
        server_name: str,
        cfg: MCPServerConfig,
        ClientSession: type,
        streamable_http_client: Any,
        create_mcp_http_client: Any | None = None,
    ) -> list[Any]:
        """Connect to a single HTTP-based MCP server (Streamable HTTP transport)."""
        if not cfg.url:
            _log.warning("MCP server '%s': no url specified for http type, skipping", server_name)
            return []

        if create_mcp_http_client is not None and callable(create_mcp_http_client):
            http_client = create_mcp_http_client(headers=cfg.headers or None)
            transport_ctx = streamable_http_client(cfg.url, http_client=http_client)
        else:
            transport_ctx = streamable_http_client(cfg.url)

        return await self._start_server_task(server_name, transport_ctx, ClientSession)

    async def close(self, keep_tools: bool = False) -> None:
        """Disconnect from all MCP servers."""
        for server_name in list(self._server_sessions.keys()):
            await self.disconnect_server(server_name, keep_tools=keep_tools)
        self._server_cleanups.clear()
        self._server_sessions.clear()
        self._server_loops.clear()
        self._server_tasks.clear()
        self._server_shutdowns.clear()
        if not keep_tools:
            self._server_tools.clear()

            self.always_allow_tools.clear()
