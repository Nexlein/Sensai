from collections.abc import AsyncGenerator

import httpx

from sensai.core.prompt import build_prompt
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Conversation, ToolCall
from sensai.domain.protocols import LLMProvider, ToolRegistry


class ChatEngine:
    def __init__(
        self,
        provider: LLMProvider,
        conversation: Conversation,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.provider = provider
        self.conversation = conversation
        self.registry = registry

    async def send(self, user_text: str) -> AsyncGenerator[Event]:
        if not user_text.strip():
            raise EmptyInputError("user_text must not be empty")

        self.conversation.add_message(role="user", content=user_text)

        for _ in range(5):
            prompt = build_prompt(self.conversation)

            chunks: list[str] = []
            tool_calls: list[ToolCallEvent] = []

            try:
                tools_schema = (
                    self.registry.get_tools_schema() if self.registry else None
                )
                async for event in self.provider.chat_stream(
                    prompt, tools=tools_schema
                ):
                    if isinstance(event, TextChunkEvent):
                        chunks.append(event.content)
                    elif isinstance(event, ToolCallEvent):
                        tool_calls.append(event)
                    yield event
            except (RuntimeError, httpx.ConnectError) as exc:
                self.conversation.messages.pop()
                raise ProviderError("provider request failed") from exc

            if not tool_calls:
                self.conversation.add_message(role="assistant", content="".join(chunks))
                break

            tcs = [
                ToolCall(name=tc.tool_name, arguments=tc.arguments) for tc in tool_calls
            ]
            self.conversation.add_message(
                role="assistant",
                content="".join(chunks),
                tool_calls=tcs,
            )

            for tc in tcs:
                tool = self.registry.get(tc.name) if self.registry else None
                if not tool:
                    result = f"Error: Tool '{tc.name}' not found in registry."
                else:
                    try:
                        result = await tool.execute(**tc.arguments)
                    except Exception as e:  # noqa: BLE001
                        result = str(e)

                self.conversation.add_message(
                    role="tool",
                    content=str(result),
                )
