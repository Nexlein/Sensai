import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from sensai.domain.events import Event, TextChunkEvent, ThoughtEvent, ToolCallEvent
from sensai.domain.models import Message


class MockLLMProvider:
    def __init__(
        self,
        default_response: str = "This is a mocked response from SENSAI.",
        simulated_delay: float = 0.02,
        thought: str | None = None,
    ) -> None:
        self.default_response = default_response
        self.simulated_delay = simulated_delay
        self.thought = thought

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        think: bool | str | None = None,
    ) -> AsyncGenerator[Event]:
        if self.thought:
            yield ThoughtEvent(content=self.thought, source="native")
        words = self.default_response.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else f" {word}"
            yield TextChunkEvent(content=chunk)
            if self.simulated_delay > 0:
                await asyncio.sleep(self.simulated_delay)


class MockToolCallingLLMProvider:
    def __init__(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        simulated_delay: float = 0.02,
    ) -> None:
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.simulated_delay = simulated_delay

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        think: bool | str | None = None,
    ) -> AsyncGenerator[Event]:
        if self.simulated_delay > 0:
            await asyncio.sleep(self.simulated_delay)

        yield ToolCallEvent(
            tool_name=self.tool_name,
            arguments=self.tool_args,
        )
