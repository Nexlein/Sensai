import difflib
import os
from pathlib import Path
from typing import Any

from .base import PermissionBoundary, SensitiveTool, Tool


class ReadFileTool(PermissionBoundary, Tool):
    name = "read_file"
    description = (
        "Read the text contents of an existing local file inside the allowed root. "
        "The path is a file, not a directory. A unique case-insensitive filename match is accepted. "
        "Use list_dir on its parent directory first if the exact filename is unknown."
    )

    def __init__(self, allowed_root: str | Path) -> None:
        super().__init__(allowed_root)
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the allowed root, for example AGENTS.md or docs/guide.md. Exact spelling is preferred.",
                }
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            target_path = self._validate_path(path)
            if not target_path.is_file() and target_path.parent.is_dir():
                matches = [
                    entry
                    for entry in target_path.parent.iterdir()
                    if entry.name.casefold() == target_path.name.casefold()
                ]
                if len(matches) == 1:
                    # Keep the same confinement check for a case-corrected symlink.
                    target_path = self._validate_path(str(matches[0]))
                elif len(matches) > 1:
                    return f"Error: Ambiguous file name: {path}"
            if not target_path.is_file():
                return f"Error: File not found or is a directory: {path}"
            return target_path.read_text(encoding="utf-8")
        except ValueError as e:
            return f"Error: {e}"
        except OSError as e:
            return f"Error reading file: {e}"


class ListDirTool(PermissionBoundary, Tool):
    name = "list_dir"
    description = (
        "List actual file and directory names inside a local directory. "
        "Use this to see what exists or find the exact spelling of a filename. "
        "Use path '.' for the allowed project root. The path must be a directory, not a file."
    )

    def __init__(self, allowed_root: str | Path) -> None:
        super().__init__(allowed_root)
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the allowed root. Use '.' for the project root, not '/'. Do not pass a filename.",
                }
            },
            "required": [],
        }

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


class WriteFileTool(PermissionBoundary, SensitiveTool):
    name = "write_file"
    description = (
        "Write text content to a local file inside the allowed root, creating it or "
        "replacing its contents. Missing parent directories are created. "
        "The user must confirm every write before it happens."
    )

    def __init__(self, allowed_root: str | Path) -> None:
        super().__init__(allowed_root)
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the allowed root, for example notes/todo.md. Do not pass a directory.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write. Existing content is replaced.",
                },
            },
            "required": ["path", "content"],
        }

    def preview(self, path: str, content: str, **kwargs: Any) -> str | None:
        """Unified diff of the write, or None when execute would refuse it."""
        try:
            target_path = self._validate_path(path)
            if target_path.is_dir():
                return None
            old = (
                target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
            )
        except (ValueError, OSError, UnicodeDecodeError):
            return None
        return "\n".join(
            difflib.unified_diff(
                old.splitlines(),
                content.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            target_path = self._validate_path(path)
            if target_path.is_dir():
                return f"Error: Path is a directory: {path}"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} characters to {path}"
        except ValueError as e:
            return f"Error: {e}"
        except OSError as e:
            return f"Error writing file: {e}"
