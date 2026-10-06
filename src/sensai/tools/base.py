import abc
from pathlib import Path
from typing import Any

from sensai.domain.protocols import BaseTool


class Tool(BaseTool, abc.ABC):
    name: str
    description: str
    parameters_schema: dict[str, Any]
    requires_confirmation: bool = False

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        pass


class SensitiveTool(Tool, abc.ABC):
    requires_confirmation: bool = True


class PermissionBoundary:
    """Resolve tool paths while keeping them inside an allowed directory."""

    def __init__(self, allowed_root: str | Path) -> None:
        self.allowed_root = Path(allowed_root).resolve()

    def _validate_path(self, path: str) -> Path:
        target_path = (self.allowed_root / path).resolve()
        if not target_path.is_relative_to(self.allowed_root):
            raise ValueError(f"Path traversal rejected: {path}")
        return target_path
