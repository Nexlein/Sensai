from typing import Any

from sensai.tools.base import Tool
from sensai.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy"
    description = "Dummy tool"

    def __init__(self) -> None:
        self.parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "dummy result"


def test_registry_register_and_get():
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    assert registry.get("dummy") is tool
    assert registry.get("nonexistent") is None


def test_registry_list_tools():
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0] is tool


def test_registry_get_tools_schema():
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    schemas = registry.get_tools_schema()
    assert len(schemas) == 1
    assert schemas[0] == {
        "type": "function",
        "function": {
            "name": "dummy",
            "description": "Dummy tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_build_default_registry_always_registers_web_search(tmp_path):
    from sensai.tools.registry import SEARXNG_URL, build_default_registry

    registry = build_default_registry(None)
    web_tool = registry.get("web_search")
    assert web_tool is not None
    assert web_tool.base_url == SEARXNG_URL
    assert {tool.name for tool in registry.list_tools()} == {"web_search"}

    with_files = build_default_registry(str(tmp_path))
    assert {tool.name for tool in with_files.list_tools()} == {
        "read_file",
        "list_dir",
        "web_search",
    }
    assert any(
        item["function"]["name"] == "web_search"
        for item in with_files.get_tools_schema()
    )
