"""Live check against the official GitHub MCP server (a third-party, preexisting one).

Opt-in: needs Docker, network access and a token in GITHUB_PERSONAL_ACCESS_TOKEN.
    SENSAI_LIVE_MCP=1 GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) \
        uv run pytest tests/tools/test_mcp_live.py

Read-only mode and the `issues` toolset only: nothing here can write to GitHub.
"""

import json
import os

import pytest

from sensai.tools.mcp import McpClient, McpTool

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("SENSAI_LIVE_MCP")
            and os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        ),
        reason="set SENSAI_LIVE_MCP=1 and GITHUB_PERSONAL_ACCESS_TOKEN (needs Docker)",
    ),
]


@pytest.fixture
async def github():
    client = McpClient(
        "docker",
        [
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "ghcr.io/github/github-mcp-server",
            "stdio",
            "--read-only",
            "--toolsets",
            "issues",
        ],
        timeout=60.0,
    )
    await client.start()
    yield client
    await client.close()


async def test_github_server_lists_its_issue_tools(github):
    names = {tool["name"] for tool in await github.list_tools()}

    assert {"list_issues", "issue_read", "search_issues"} <= names


async def test_github_tool_call_goes_through_mcp_tool(github):
    definitions = {tool["name"]: tool for tool in await github.list_tools()}
    tool = McpTool(github, "github", definitions["list_issues"])

    result = await tool.execute(owner="Nexlein", repo="Sensai", state="OPEN")

    assert tool.name == "github__list_issues"
    assert tool.requires_confirmation is True
    assert isinstance(json.loads(result)["issues"], list)
