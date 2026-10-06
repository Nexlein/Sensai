from pathlib import Path
from typing import Any

import pytest

from sensai.tools.base import PermissionBoundary, SensitiveTool, Tool
from sensai.tools.web import WebSearch


def test_permission_boundary_accepts_paths_inside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    assert PermissionBoundary(root)._validate_path("nested/file.txt") == (
        root / "nested/file.txt"
    )


def test_permission_boundary_rejects_paths_outside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="Path traversal rejected"):
        PermissionBoundary(root)._validate_path("../secret.txt")


class _PlainTool(Tool):
    name = "plain"
    description = "plain"

    def __init__(self) -> None:
        self.parameters_schema: dict[str, Any] = {}

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class _RiskyTool(SensitiveTool):
    name = "risky"
    description = "risky"

    def __init__(self) -> None:
        self.parameters_schema: dict[str, Any] = {}

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


def test_tool_does_not_require_confirmation_by_default():
    assert _PlainTool().requires_confirmation is False


def test_sensitive_tool_requires_confirmation():
    assert _RiskyTool().requires_confirmation is True
    assert isinstance(_RiskyTool(), Tool)


def test_web_search_is_sensitive():
    assert issubclass(WebSearch, SensitiveTool)
    assert WebSearch("http://localhost").requires_confirmation is True
