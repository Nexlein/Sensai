from typing import Any

from sensai.tools.base import Tool
from sensai.tools.registry import ToolRegistry, build_default_registry


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


def test_default_registry_includes_extra_tools():
    extra = DummyTool()

    registry = build_default_registry(None, extra_tools=[extra])

    assert registry.get("dummy") is extra
    assert registry.get("web_search") is not None
    assert registry.get("read_file") is None


def test_default_registry_builtins_win_a_name_clash():
    class FakeWebSearch(DummyTool):
        name = "web_search"

    registry = build_default_registry(None, extra_tools=[FakeWebSearch()])

    assert not isinstance(registry.get("web_search"), FakeWebSearch)


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
    assert {tool.name for tool in registry.list_tools()} == {"web_search", "run_python"}

    with_files = build_default_registry(str(tmp_path))
    assert {tool.name for tool in with_files.list_tools()} == {
        "read_file",
        "list_dir",
        "write_file",
        "web_search",
        "run_python",
    }
    assert any(
        item["function"]["name"] == "web_search"
        for item in with_files.get_tools_schema()
    )


def test_build_default_registry_with_memory(tmp_path):
    from sensai.memory.manager import SqliteMemoryManager
    from sensai.tools.registry import build_default_registry

    memory = SqliteMemoryManager(tmp_path / "mem.db")
    registry = build_default_registry(str(tmp_path), memory=memory)
    names = {tool.name for tool in registry.list_tools()}
    assert "remember_fact" in names
    assert "recall_memory" in names
    assert "forget_fact" in names
