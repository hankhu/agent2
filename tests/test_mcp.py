"""Tests for agent2.mcp — MCP server config and tool wrapping."""

from agent2.mcp import MCPServerConfig, _make_mcp_tool


def test_mcp_server_config_stdio():
    cfg = MCPServerConfig(command="npx", args=["-y", "server"], env={"FOO": "bar"})
    assert cfg.command == "npx"
    assert cfg.args == ["-y", "server"]
    assert cfg.env == {"FOO": "bar"}
    assert cfg.url is None


def test_mcp_server_config_sse():
    cfg = MCPServerConfig(url="http://localhost:8080/sse")
    assert cfg.url == "http://localhost:8080/sse"
    assert cfg.command is None


def test_mcp_server_config_from_dict():
    data = {"command": "node", "args": ["server.js"], "env": {"KEY": "val"}}
    cfg = MCPServerConfig.model_validate(data)
    assert cfg.command == "node"
    assert cfg.args == ["server.js"]


async def test_make_mcp_tool():
    """Verify _make_mcp_tool wraps correctly as an agent2 Tool."""
    async def fake_call(**kwargs):
        return f"result: {kwargs}"

    tool = _make_mcp_tool(
        name="test_tool",
        description="A test tool",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        },
        call_fn=fake_call,
    )

    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool.schema.name == "test_tool"
    assert len(tool.schema.parameters) == 2

    # Check parameter details
    params = {p.name: p for p in tool.schema.parameters}
    assert params["query"].required is True
    assert params["query"].type == "string"
    assert params["limit"].required is False
    assert params["limit"].type == "integer"

    # Check execution
    result = await tool.execute(query="hello")
    assert "hello" in result


def test_mcp_manager_init():
    from agent2.mcp import MCPManager

    servers = {"fs": MCPServerConfig(command="npx", args=["server"])}
    manager = MCPManager(servers)
    assert len(manager._server_configs) == 1


def test_mcp_server_config_sse_full():
    data = {
        "type": "sse",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer test-token"},
        "disabled": False,
        "alwaysAllow": ["tool1", "tool2"],
    }
    cfg = MCPServerConfig.model_validate(data)
    assert cfg.type == "sse"
    assert cfg.url == "https://example.com/mcp"
    assert cfg.headers == {"Authorization": "Bearer test-token"}
    assert cfg.disabled is False
    assert cfg.always_allow == ["tool1", "tool2"]


def test_mcp_server_config_defaults():
    cfg = MCPServerConfig(url="https://example.com/mcp")
    assert cfg.type == "sse"
    assert cfg.headers == {}
    assert cfg.disabled is False
    assert cfg.always_allow == []


def test_mcp_server_config_type_inference():
    # Only command provided -> stdio
    c1 = MCPServerConfig.model_validate({"command": "npx", "args": ["foo"]})
    assert c1.type == "stdio"

    # Both command and type explicitly given -> type wins
    c2 = MCPServerConfig.model_validate({"type": "stdio", "command": "npx"})
    assert c2.type == "stdio"

    # Only url provided -> sse
    c3 = MCPServerConfig.model_validate({"url": "https://api.example.com"})
    assert c3.type == "sse"

    # Both type="sse" and url
    c4 = MCPServerConfig.model_validate({"type": "sse", "url": "https://api.example.com"})
    assert c4.type == "sse"

    # type="http"
    c5 = MCPServerConfig.model_validate({"type": "http", "url": "https://api.example.com"})
    assert c5.type == "http"

    # type="streamable_http" -> normalized to "http"
    c6 = MCPServerConfig.model_validate({"type": "streamable_http", "url": "https://api.example.com"})
    assert c6.type == "http"


def test_mcp_server_config_always_allow_aliases():
    c_camel = MCPServerConfig.model_validate({"url": "http://x", "alwaysAllow": ["a", "b"]})
    assert c_camel.always_allow == ["a", "b"]

    c_snake = MCPServerConfig.model_validate({"url": "http://x", "always_allow": ["c", "d"]})
    assert c_snake.always_allow == ["c", "d"]


def test_mcp_server_config_disabled():
    cfg = MCPServerConfig(url="http://x", disabled=True)
    assert cfg.disabled is True


async def test_mcp_manager_disabled_server_skipped(monkeypatch):
    from unittest.mock import AsyncMock
    from agent2.mcp import MCPManager

    import sys
    import types

    fake_mcp = types.ModuleType("mcp")
    fake_mcp.ClientSession = object  # type: ignore[attr-defined]
    fake_mcp_client = types.ModuleType("mcp.client")
    fake_mcp_sse = types.ModuleType("mcp.client.sse")
    fake_mcp_sse.sse_client = object  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", fake_mcp_sse)

    servers = {
        "disabled_srv": MCPServerConfig(url="http://disabled", disabled=True),
        "active_srv": MCPServerConfig(url="http://active", disabled=False),
    }
    manager = MCPManager(servers)

    mock_connect_sse = AsyncMock(return_value=[])
    monkeypatch.setattr(manager, "_connect_sse", mock_connect_sse)

    await manager.connect()
    assert mock_connect_sse.call_count == 1
    call_args = mock_connect_sse.call_args[0]
    assert call_args[0] == "active_srv"


async def test_mcp_manager_always_allow_collection(monkeypatch):
    from agent2.mcp import MCPManager

    import sys
    import types

    fake_mcp = types.ModuleType("mcp")
    fake_mcp.ClientSession = object  # type: ignore[attr-defined]
    fake_mcp_client = types.ModuleType("mcp.client")
    fake_mcp_sse = types.ModuleType("mcp.client.sse")
    fake_mcp_sse.sse_client = object  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", fake_mcp_sse)

    t1 = _make_mcp_tool("tool1", "d1", {}, lambda **kw: "")
    t2 = _make_mcp_tool("tool2", "d2", {}, lambda **kw: "")
    t3 = _make_mcp_tool("tool3", "d3", {}, lambda **kw: "")

    servers = {
        "srv1": MCPServerConfig(url="http://srv1", alwaysAllow=["tool1"]),
        "srv2": MCPServerConfig(url="http://srv2", alwaysAllow=["*"]),
    }
    manager = MCPManager(servers)

    async def fake_connect(name, cfg, *args):
        if name == "srv1":
            return [t1]
        return [t2, t3]

    monkeypatch.setattr(manager, "_connect_sse", fake_connect)

    tools = await manager.connect()
    assert len(tools) == 3
    assert "tool1" in manager.always_allow_tools
    assert "tool2" in manager.always_allow_tools
    assert "tool3" in manager.always_allow_tools


async def test_mcp_manager_connect_sse_missing_url():
    from agent2.mcp import MCPManager

    cfg = MCPServerConfig(type="sse", url=None)
    manager = MCPManager({"test": cfg})
    tools = await manager._connect_sse("test", cfg, object, object)
    assert tools == []


def test_build_tui_agent_mcp_always_allow(monkeypatch):
    from unittest.mock import patch, AsyncMock
    from agent2.app.tui.app import build_tui_agent
    from agent2.app.config import AppConfig

    fake_cfg = AppConfig(
        mcp_servers={
            "my_server": {
                "url": "http://example.com/sse",
                "alwaysAllow": ["special_tool"],
            }
        }
    )
    monkeypatch.setattr("agent2.app.tui.app.load_config", lambda: fake_cfg)
    monkeypatch.setattr("agent2.app.tui.app.create_llm", lambda *a, **k: object())

    mock_tool = _make_mcp_tool("special_tool", "desc", {}, lambda **kw: "")
    mock_manager = AsyncMock()
    mock_manager.connect.return_value = [mock_tool]
    mock_manager.always_allow_tools = {"special_tool"}

    with patch("agent2.mcp.MCPManager", return_value=mock_manager):
        agent = build_tui_agent(no_tools=False)
        assert "special_tool" in agent._auto_approved


async def test_mcp_manager_connect_sse_flow():
    from unittest.mock import AsyncMock, MagicMock
    from agent2.mcp import MCPManager

    cfg = MCPServerConfig(
        type="sse",
        url="https://api.example.com/sse",
        headers={"Authorization": "Bearer token123"},
    )
    manager = MCPManager({"test": cfg})

    fake_tool_def = MagicMock()
    fake_tool_def.name = "sse_echo"
    fake_tool_def.description = "Echo back"
    fake_tool_def.inputSchema = {"properties": {}}

    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_result = MagicMock()
    fake_result.tools = [fake_tool_def]
    fake_session.list_tools = AsyncMock(return_value=fake_result)

    block = MagicMock()
    block.text = "echo response"
    fake_call_resp = MagicMock()
    fake_call_resp.content = [block]
    fake_session.call_tool = AsyncMock(return_value=fake_call_resp)

    class FakeSessionCtx:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *args):
            pass

    captured = {}

    def fake_sse_client(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers

        class FakeTransportCtx:
            async def __aenter__(self):
                return ("read_stream", "write_stream")

            async def __aexit__(self, *args):
                pass

        return FakeTransportCtx()

    tools = await manager._connect_sse(
        "test",
        cfg,
        lambda r, w: FakeSessionCtx(),
        fake_sse_client,
    )
    assert len(tools) == 1
    assert tools[0].name == "sse_echo"
    assert captured["url"] == "https://api.example.com/sse"
    assert captured["headers"] == {"Authorization": "Bearer token123"}

    res = await tools[0].execute()
    assert res == "echo response"

    await manager.close()
    assert len(manager._cleanup_fns) == 0
    assert len(manager._sessions) == 0


def test_update_mcp_server_disabled(tmp_path, monkeypatch):
    import json
    from agent2.app.config import update_mcp_server_disabled

    cfg_file = tmp_path / "config.json"
    data = {
        "mcp_servers": {
            "srv1": {"url": "http://srv1", "disabled": False},
            "srv2": {"url": "http://srv2", "disabled": True},
        }
    }
    cfg_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr("agent2.app.config.CONFIG_FILE", cfg_file)

    # Disable srv1
    ok = update_mcp_server_disabled("srv1", True)
    assert ok is True
    updated = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert updated["mcp_servers"]["srv1"]["disabled"] is True

    # Enable srv2
    ok = update_mcp_server_disabled("srv2", False)
    assert ok is True
    updated = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert updated["mcp_servers"]["srv2"]["disabled"] is False

    # Unknown server
    assert update_mcp_server_disabled("unknown", True) is False


async def test_mcp_manager_connect_and_disconnect_server(monkeypatch):
    from agent2.mcp import MCPManager

    import sys
    import types

    fake_mcp = types.ModuleType("mcp")
    fake_mcp.ClientSession = object  # type: ignore[attr-defined]
    fake_mcp_client = types.ModuleType("mcp.client")
    fake_mcp_sse = types.ModuleType("mcp.client.sse")
    fake_mcp_sse.sse_client = object  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", fake_mcp_sse)

    t1 = _make_mcp_tool("custom_tool_1", "d1", {}, lambda **kw: "")
    t2 = _make_mcp_tool("custom_tool_2", "d2", {}, lambda **kw: "")

    servers = {
        "my_srv": MCPServerConfig(url="http://mysrv", alwaysAllow=["custom_tool_1"]),
    }
    manager = MCPManager(servers)

    async def fake_connect(name, cfg, *args):
        # simulate cleanup registration
        manager._server_cleanups[name] = [AsyncMock()]
        manager._server_sessions[name] = object()
        return [t1, t2]

    from unittest.mock import AsyncMock
    monkeypatch.setattr(manager, "_connect_sse", fake_connect)

    # Connect server
    tools = await manager.connect_server("my_srv")
    assert len(tools) == 2
    assert manager.is_server_connected("my_srv") is True
    assert len(manager.get_server_tools("my_srv")) == 2
    assert "custom_tool_1" in manager.always_allow_tools

    # Disconnect server
    removed = await manager.disconnect_server("my_srv")
    assert removed == ["custom_tool_1", "custom_tool_2"]
    assert manager.is_server_connected("my_srv") is False
    assert len(manager.get_server_tools("my_srv")) == 0
    assert "custom_tool_1" not in manager.always_allow_tools


async def test_mcp_manager_call_tool_auto_reconnect(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from agent2.mcp import MCPManager

    cfg = MCPServerConfig(type="sse", url="http://example.com/sse")
    manager = MCPManager({"test": cfg})

    reconnected = []

    async def fake_connect(name):
        reconnected.append(name)
        fake_session = AsyncMock()
        mock_resp = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "reconnected response"
        mock_resp.content = [mock_block]
        fake_session.call_tool.return_value = mock_resp
        manager._server_sessions[name] = fake_session
        manager._server_loops[name] = asyncio.get_running_loop()
        return []

    monkeypatch.setattr(manager, "connect_server", fake_connect)

    # Server is not connected yet
    assert manager.is_server_connected("test") is False

    # call_tool should auto-connect
    res = await manager.call_tool("test", "echo", {"msg": "hello"})
    assert res == "reconnected response"
    assert "test" in reconnected
    assert manager.is_server_connected("test") is True


async def test_mcp_manager_connect_http_missing_url():
    from agent2.mcp import MCPManager

    cfg = MCPServerConfig(type="http", url=None)
    manager = MCPManager({"test": cfg})
    tools = await manager._connect_http("test", cfg, object, object)
    assert tools == []


async def test_mcp_manager_connect_http_flow():
    from unittest.mock import AsyncMock, MagicMock
    from agent2.mcp import MCPManager

    cfg = MCPServerConfig(
        type="http",
        url="https://api.example.com/mcp",
        headers={"Authorization": "Bearer http-token"},
    )
    manager = MCPManager({"test": cfg})

    fake_tool_def = MagicMock()
    fake_tool_def.name = "http_calculator"
    fake_tool_def.description = "Add two numbers"
    fake_tool_def.inputSchema = {"properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}

    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_result = MagicMock()
    fake_result.tools = [fake_tool_def]
    fake_session.list_tools = AsyncMock(return_value=fake_result)

    block = MagicMock()
    block.text = "sum: 42"
    fake_call_resp = MagicMock()
    fake_call_resp.content = [block]
    fake_session.call_tool = AsyncMock(return_value=fake_call_resp)

    class FakeSessionCtx:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *args):
            pass

    captured = {}

    def fake_create_mcp_http_client(headers=None):
        captured["headers"] = headers
        return "mock_http_client"

    def fake_streamable_http_client(url, http_client=None):
        captured["url"] = url
        captured["http_client"] = http_client

        class FakeTransportCtx:
            async def __aenter__(self):
                return ("read_stream", "write_stream")

            async def __aexit__(self, *args):
                pass

        return FakeTransportCtx()

    tools = await manager._connect_http(
        "test",
        cfg,
        lambda r, w: FakeSessionCtx(),
        fake_streamable_http_client,
        fake_create_mcp_http_client,
    )
    assert len(tools) == 1
    assert tools[0].name == "http_calculator"
    assert captured["url"] == "https://api.example.com/mcp"
    assert captured["headers"] == {"Authorization": "Bearer http-token"}
    assert captured["http_client"] == "mock_http_client"

    res = await tools[0].execute()
    assert res == "sum: 42"

    await manager.close()
    assert len(manager._cleanup_fns) == 0
    assert len(manager._sessions) == 0


async def test_mcp_manager_fallback_sse_to_http(monkeypatch):
    from unittest.mock import AsyncMock
    from agent2.mcp import MCPManager

    import sys
    import types

    fake_mcp = types.ModuleType("mcp")
    fake_mcp.ClientSession = object  # type: ignore[attr-defined]
    fake_mcp_client = types.ModuleType("mcp.client")
    fake_mcp_sse = types.ModuleType("mcp.client.sse")
    fake_mcp_sse.sse_client = object  # type: ignore[attr-defined]
    fake_mcp_sh = types.ModuleType("mcp.client.streamable_http")
    fake_mcp_sh.streamable_http_client = object  # type: ignore[attr-defined]
    fake_mcp_sh.create_mcp_http_client = object  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", fake_mcp_sse)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", fake_mcp_sh)

    cfg = MCPServerConfig(type="sse", url="http://example.com/mcp")
    manager = MCPManager({"test": cfg})

    tool = _make_mcp_tool("http_tool", "desc", {}, lambda **kw: "")
    mock_connect_sse = AsyncMock(side_effect=RuntimeError("SSE not supported"))
    mock_connect_http = AsyncMock(return_value=[tool])

    monkeypatch.setattr(manager, "_connect_sse", mock_connect_sse)
    monkeypatch.setattr(manager, "_connect_http", mock_connect_http)

    tools = await manager.connect_server("test")
    assert len(tools) == 1
    assert tools[0].name == "http_tool"
    assert mock_connect_sse.call_count == 1
    assert mock_connect_http.call_count == 1



