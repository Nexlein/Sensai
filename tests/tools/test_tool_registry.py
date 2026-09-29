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


def test_build_default_registry_registers_file_tools_only_when_allowed(tmp_path):
    from sensai.tools.registry import build_default_registry

    assert build_default_registry(None).get_tools_schema() == []
    registry = build_default_registry(str(tmp_path))
    assert {tool.name for tool in registry.list_tools()} == {"read_file", "list_dir"}
