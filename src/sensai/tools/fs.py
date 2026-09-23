import os
from pathlib import Path
from typing import Any

from .base import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file"

    def __init__(self, allowed_root: str | Path) -> None:
        self.allowed_root = Path(allowed_root).resolve()
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to read",
                }
            },
            "required": ["path"],
        }

    def _validate_path(self, path: str) -> Path:
        target_path = (self.allowed_root / path).resolve()
        if not target_path.is_relative_to(self.allowed_root):
            raise ValueError(f"Path traversal rejected: {path}")
        return target_path

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            target_path = self._validate_path(path)
            if not target_path.is_file():
                return f"Error: File not found or is a directory: {path}"
            return target_path.read_text(encoding="utf-8")
        except ValueError as e:
            return f"Error: {e}"
        except OSError as e:
            return f"Error reading file: {e}"


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the contents of a directory"

    def __init__(self, allowed_root: str | Path) -> None:
        self.allowed_root = Path(allowed_root).resolve()
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the directory to list. Leave empty or use '.' for the root directory.",
                }
            },
            "required": [],
        }

    def _validate_path(self, path: str) -> Path:
        target_path = (self.allowed_root / path).resolve()
        if not target_path.is_relative_to(self.allowed_root):
            raise ValueError(f"Path traversal rejected: {path}")
        return target_path

    async def execute(self, path: str = ".", **kwargs: Any) -> str:
        try:
            target_path = self._validate_path(path)
            if not target_path.is_dir():
                return f"Error: Directory not found or is a file: {path}"
            entries = os.listdir(target_path)
            return "\n".join(entries) if entries else "(empty directory)"
        except ValueError as e:
            return f"Error: {e}"
        except OSError as e:
            return f"Error listing directory: {e}"
