from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest

from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation, Message
from sensai.providers.mock import MockLLMProvider


class FailingLLMProvider:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]:
        raise self.exc
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_send_accumulates_chunks_into_single_assistant_message():
    conversation = Conversation()
    provider = MockLLMProvider(default_response="hello world", simulated_delay=0)
    engine = ChatEngine(provider, conversation)

    events = [event async for event in engine.send("hi")]

    assert len(events) > 0
    assert conversation.messages[-1].role == "assistant"
    assert conversation.messages[-1].content == "hello world"
    assert len([m for m in conversation.messages if m.role == "assistant"]) == 1


@pytest.mark.asyncio
async def test_send_rejects_empty_input_before_provider_call():
    conversation = Conversation()
    provider = MockLLMProvider(simulated_delay=0)
    engine = ChatEngine(provider, conversation)

    with pytest.raises(EmptyInputError):
        async for _ in engine.send("   "):
            pass

    assert conversation.messages == []


@pytest.mark.asyncio
async def test_send_wraps_provider_runtime_error_and_leaves_conversation_unchanged():
    conversation = Conversation()
    provider = FailingLLMProvider(RuntimeError("HTTP Provider Error [500]: boom"))
    engine = ChatEngine(provider, conversation)

    with pytest.raises(ProviderError):
        async for _ in engine.send("hi"):
            pass

    assert conversation.messages == []


@pytest.mark.asyncio
async def test_send_wraps_provider_connect_error_and_leaves_conversation_unchanged():
    conversation = Conversation()
    provider = FailingLLMProvider(httpx.ConnectError("connection refused"))
    engine = ChatEngine(provider, conversation)

    with pytest.raises(ProviderError):
        async for _ in engine.send("hi"):
            pass

    assert conversation.messages == []
