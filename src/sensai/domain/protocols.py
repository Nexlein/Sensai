from collections.abc import AsyncGenerator
from typing import Any, Protocol

from sensai.domain.events import Event
from sensai.domain.models import Conversation, Message


class LLMProvider(Protocol):
    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]: ...


class BaseTool(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]

    async def execute(self, **kwargs: Any) -> str: ...


class MemoryStore(Protocol):
    async def save(self, conversation: Conversation) -> None: ...

    async def load(self, conversation_id: str) -> Conversation | None: ...


class Guardrail(Protocol):
    async def filter_input(self, text: str) -> str: ...

    async def filter_output(self, text: str) -> str: ...


class ToolRegistry(Protocol):
    def get(self, name: str) -> BaseTool | None: ...

    def get_tools_schema(self) -> list[dict[str, Any]]: ...
