from typing import Any

from sensai.domain.protocols import BaseTool
from sensai.tools.fs import ListDirTool, ReadFileTool, WriteFileTool
from sensai.tools.web import WebSearch

SEARXNG_URL = "http://127.0.0.1:8888"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_tools_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in self._tools.values()
        ]


def build_default_registry(allowed_root: str | None) -> ToolRegistry:
    registry = ToolRegistry()
    if allowed_root is not None:
        registry.register(ReadFileTool(allowed_root))
        registry.register(ListDirTool(allowed_root))
        registry.register(WriteFileTool(allowed_root))
    registry.register(WebSearch(SEARXNG_URL))
    return registry
