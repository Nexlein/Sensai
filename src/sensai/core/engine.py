from collections.abc import AsyncGenerator

import httpx

from sensai.core.prompt import build_prompt
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent
from sensai.domain.models import Conversation
from sensai.domain.protocols import LLMProvider


class ChatEngine:
    def __init__(self, provider: LLMProvider, conversation: Conversation) -> None:
        self.provider = provider
        self.conversation = conversation

    async def send(self, user_text: str) -> AsyncGenerator[Event]:
        if not user_text.strip():
            raise EmptyInputError("user_text must not be empty")

        self.conversation.add_message(role="user", content=user_text)
        prompt = build_prompt(self.conversation)

        chunks: list[str] = []
        try:
            async for event in self.provider.chat_stream(prompt):
                if isinstance(event, TextChunkEvent):
                    chunks.append(event.content)
                yield event
        except (RuntimeError, httpx.ConnectError) as exc:
            self.conversation.messages.pop()
            raise ProviderError("provider request failed") from exc

        self.conversation.add_message(role="assistant", content="".join(chunks))
