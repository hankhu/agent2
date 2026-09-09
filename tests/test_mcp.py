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
