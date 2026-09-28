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
