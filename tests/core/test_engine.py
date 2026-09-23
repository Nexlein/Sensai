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


from sensai.domain.events import TextChunkEvent, ToolCallEvent
from sensai.providers.mock import MockToolCallingLLMProvider
from sensai.tools.registry import ToolRegistry


class DummyTool:
    name = "dummy"
    description = "a dummy tool"
    parameters_schema = {}  # noqa: RUF012

    def __init__(self, return_val="success", exc=None):
        self.return_val = return_val
        self.exc = exc

    async def execute(self, **kwargs):
        if self.exc:
            raise self.exc
        return self.return_val


class MockRoundTripProvider:
    def __init__(self):
        self.calls = 0

    async def chat_stream(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield ToolCallEvent(tool_name="dummy", arguments={"foo": "bar"})
        else:
            yield TextChunkEvent(content="final")
            yield TextChunkEvent(content=" answer")


@pytest.mark.asyncio
async def test_normal_tool_round_trip():
    conversation = Conversation()
    provider = MockRoundTripProvider()
    registry = ToolRegistry()
    registry.register(DummyTool(return_val="dummy_result"))
    engine = ChatEngine(provider, conversation, registry)

    _ = [e async for e in engine.send("do it")]

    # User message + Assistant (tool call) + Tool message + Assistant (final)
    assert len(conversation.messages) == 4
    assert conversation.messages[1].role == "assistant"
    assert conversation.messages[1].tool_calls[0].name == "dummy"
    assert conversation.messages[2].role == "tool"
    assert conversation.messages[2].content == "dummy_result"
    assert conversation.messages[3].role == "assistant"
    assert conversation.messages[3].content == "final answer"


@pytest.mark.asyncio
async def test_infinite_tool_call_loop_caps_at_5():
    conversation = Conversation()
    provider = MockToolCallingLLMProvider("dummy", {})
    registry = ToolRegistry()
    registry.register(DummyTool())
    engine = ChatEngine(provider, conversation, registry)

    _ = [e async for e in engine.send("go")]

    # 1 user + 5 pairs of (assistant tool_call, tool result) = 11 messages
    assert len(conversation.messages) == 11
    tool_messages = [m for m in conversation.messages if m.role == "tool"]
    assert len(tool_messages) == 5


@pytest.mark.asyncio
async def test_tool_unexpected_exception():
    conversation = Conversation()
    provider = MockRoundTripProvider()
    registry = ToolRegistry()
    registry.register(DummyTool(exc=RuntimeError("boom")))
    engine = ChatEngine(provider, conversation, registry)

    _ = [e async for e in engine.send("do it")]

    assert len(conversation.messages) == 4
    assert conversation.messages[2].role == "tool"
    assert "boom" in conversation.messages[2].content
    assert conversation.messages[3].role == "assistant"
    assert conversation.messages[3].content == "final answer"
