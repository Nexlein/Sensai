import sys
from pathlib import Path

import pytest

from sensai.tools.mcp import McpClient, McpError, McpTool

SERVER = str(Path(__file__).with_name("mcp_test_server.py"))


def _client(*flags: str, timeout: float = 10.0) -> McpClient:
    return McpClient(sys.executable, [SERVER, *flags], timeout=timeout)


@pytest.fixture
async def client():
    mcp = _client()
    await mcp.start()
    yield mcp
    await mcp.close()


async def test_handshake_then_list_tools(client):
    tools = await client.list_tools()

    assert [tool["name"] for tool in tools] == ["add", "boom", "image"]


async def test_call_tool_returns_text(client):
    assert await client.call_tool("add", {"a": 2, "b": 3}) == "5"


async def test_tool_error_flag_becomes_error_string(client):
    assert await client.call_tool("boom", {}) == "Error: it broke"


async def test_non_text_content_is_replaced_by_a_marker(client):
    assert await client.call_tool("image", {}) == "[image content omitted]"


async def test_protocol_error_raises(client):
    with pytest.raises(McpError, match="unknown tool"):
        await client.call_tool("nope", {})


async def test_start_fails_cleanly_when_command_is_missing():
    with pytest.raises(McpError, match="cannot start"):
        await McpClient("definitely-not-a-command-sensai").start()


async def test_start_fails_when_server_exits_during_handshake():
    with pytest.raises(McpError, match="exited unexpectedly"):
        await McpClient(sys.executable, ["-c", "pass"]).start()


async def test_server_crash_during_call_raises():
    mcp = _client("--crash-on-call")
    await mcp.start()
    try:
        with pytest.raises(McpError, match="exited unexpectedly"):
            await mcp.call_tool("add", {"a": 1, "b": 1})
    finally:
        await mcp.close()


async def test_hanging_call_times_out():
    mcp = _client("--hang-on-call", timeout=0.5)
    await mcp.start()
    try:
        with pytest.raises(McpError, match="timed out"):
            await mcp.call_tool("add", {"a": 1, "b": 1})
    finally:
        await mcp.close()


async def test_close_is_idempotent():
    mcp = _client()
    await mcp.start()
    await mcp.close()
    await mcp.close()


async def test_call_after_close_raises():
    mcp = _client()
    await mcp.start()
    await mcp.close()

    with pytest.raises(McpError, match="not running"):
        await mcp.call_tool("add", {"a": 1, "b": 1})


async def test_mcp_tool_wraps_a_remote_definition(client):
    definition = (await client.list_tools())[0]

    tool = McpTool(client, "demo", definition)

    assert tool.name == "demo__add"
    assert tool.description == "Add two numbers."
    assert tool.parameters_schema == definition["inputSchema"]
    assert tool.requires_confirmation is True
    assert await tool.execute(a=4, b=5) == "9"


async def test_mcp_tool_falls_back_when_description_and_schema_are_missing(client):
    tool = McpTool(client, "demo", {"name": "boom"})

    assert tool.description == "boom (MCP: demo)"
    assert tool.parameters_schema == {"type": "object", "properties": {}}


async def test_mcp_tool_turns_client_errors_into_strings():
    mcp = _client("--crash-on-call")
    await mcp.start()
    tool = McpTool(mcp, "demo", {"name": "add"})
    try:
        assert await tool.execute(a=1, b=1) == "Error: MCP server exited unexpectedly"
    finally:
        await mcp.close()
