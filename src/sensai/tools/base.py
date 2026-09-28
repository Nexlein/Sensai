import abc
from typing import Any

from sensai.domain.protocols import BaseTool


class Tool(BaseTool, abc.ABC):
    name: str
    description: str
    parameters_schema: dict[str, Any]

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        pass
