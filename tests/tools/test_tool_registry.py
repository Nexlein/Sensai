import inspect
import json
import re
from typing import Any

import pytest

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


def test_build_default_registry_registers_web_search_and_sandbox_by_default():
    registry = build_default_registry(None)

    assert registry.get("web_search") is not None
    assert registry.get("run_python") is not None


def test_build_default_registry_can_leave_out_web_search_and_sandbox():
    registry = build_default_registry(None, web_search=False, sandbox=False)

    names = {schema["function"]["name"] for schema in registry.get_tools_schema()}
    assert "web_search" not in names
    assert "run_python" not in names


# Contract: what every built-in tool promises the model and the engine.

BUILTIN_TOOLS = [
    "forget_fact",
    "list_dir",
    "read_file",
    "recall_memory",
    "remember_fact",
    "run_python",
    "web_search",
    "write_file",
]
# Tools with side effects or outside reach: the user confirms each call (A3).
CONFIRMED_TOOLS = {"forget_fact", "run_python", "web_search", "write_file"}
# Ollama and OpenAI-style APIs accept only these function names.
FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@pytest.fixture
def builtin_registry(tmp_path):
    from sensai.memory.manager import SqliteMemoryManager

    memory = SqliteMemoryManager(tmp_path / "memory.db")
    return build_default_registry(str(tmp_path), memory=memory)


def test_default_registry_offers_every_builtin_tool(builtin_registry):
    assert sorted(t.name for t in builtin_registry.list_tools()) == BUILTIN_TOOLS


def test_only_tools_with_side_effects_ask_for_confirmation(builtin_registry):
    confirmed = {
        t.name for t in builtin_registry.list_tools() if t.requires_confirmation
    }

    assert confirmed == CONFIRMED_TOOLS


@pytest.mark.parametrize("name", BUILTIN_TOOLS)
def test_tool_schema_is_usable_by_the_model(builtin_registry, name):
    tool = builtin_registry.get(name)
    schema = tool.parameters_schema

    assert FUNCTION_NAME.match(tool.name)
    assert tool.description.strip()
    assert schema["type"] == "object"
    assert set(schema.get("required", [])) <= set(schema["properties"])
    for prop, spec in schema["properties"].items():
        assert spec.get("type"), f"{name}.{prop} has no type"
        assert spec.get("description", "").strip(), f"{name}.{prop} is undocumented"
    json.dumps(schema)  # sent as-is in the request body


@pytest.mark.parametrize("name", BUILTIN_TOOLS)
def test_execute_accepts_exactly_what_the_schema_announces(builtin_registry, name):
    tool = builtin_registry.get(name)
    schema = tool.parameters_schema
    parameters = inspect.signature(tool.execute).parameters.values()
    mandatory = {
        p.name
        for p in parameters
        if p.default is inspect.Parameter.empty
        and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
    }

    # Every announced argument can be passed by keyword...
    inspect.signature(tool.execute).bind(
        **{prop: None for prop in schema["properties"]}
    )
    # ...and nothing the schema calls optional is mandatory in Python.
    assert mandatory <= set(schema.get("required", []))
