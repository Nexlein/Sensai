import json

import httpx
import pytest

from sensai.domain.events import TextChunkEvent, ToolCallEvent
from sensai.domain.models import Message, ToolCall
from sensai.providers.ollama import OllamaLLMProvider


def _lines_response(lines: list[dict], status_code: int = 200) -> httpx.MockTransport:
    body = "\n".join(json.dumps(line) for line in lines)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.MockTransport(handler)


def _patch_client(provider: OllamaLLMProvider, transport: httpx.MockTransport) -> None:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=provider.base_url, timeout=provider.timeout, transport=transport
        )

    provider._get_client = _get_client


def test_format_message_without_tool_calls():
    provider = OllamaLLMProvider()
    msg = Message(role="user", content="hi")
    assert provider._format_message(msg) == {"role": "user", "content": "hi"}


def test_format_message_with_tool_calls():
    provider = OllamaLLMProvider()
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="search", arguments={"q": "x"})],
    )
    payload = provider._format_message(msg)
    assert payload["tool_calls"] == [
        {"function": {"name": "search", "arguments": {"q": "x"}}}
    ]


def test_parse_line_text_content():
    provider = OllamaLLMProvider()
    line = json.dumps({"message": {"content": "hello"}})
    events = provider._parse_line(line)
    assert len(events) == 1
    assert isinstance(events[0], TextChunkEvent)
    assert events[0].content == "hello"


def test_parse_line_tool_calls():
    provider = OllamaLLMProvider()
    line = json.dumps(
        {
            "message": {
                "tool_calls": [
                    {"function": {"name": "search", "arguments": {"q": "x"}}}
                ]
            }
        }
    )
    events = provider._parse_line(line)
    assert len(events) == 1
    assert isinstance(events[0], ToolCallEvent)
    assert events[0].tool_name == "search"
    assert events[0].arguments == {"q": "x"}


def test_parse_line_empty_content_yields_no_text_event():
    provider = OllamaLLMProvider()
    line = json.dumps({"message": {"content": ""}})
    assert provider._parse_line(line) == []


async def test_chat_stream_yields_text_chunks():
    provider = OllamaLLMProvider(model="llama3.2")
    transport = _lines_response(
        [
            {"message": {"content": "Hello"}},
            {"message": {"content": " world"}},
        ]
    )
    _patch_client(provider, transport)

    msg = Message(role="user", content="hi")
    events = [e async for e in provider.chat_stream(messages=[msg])]

    assert [e.content for e in events] == ["Hello", " world"]


async def test_chat_stream_yields_tool_call_then_text():
    provider = OllamaLLMProvider()
    transport = _lines_response(
        [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": {"q": "x"}}}
                    ],
                    "content": "using tool",
                }
            }
        ]
    )
    _patch_client(provider, transport)

    events = [e async for e in provider.chat_stream(messages=[])]

    assert isinstance(events[0], ToolCallEvent)
    assert events[0].tool_name == "search"
    assert isinstance(events[1], TextChunkEvent)
    assert events[1].content == "using tool"


async def test_chat_stream_raises_on_http_error():
    provider = OllamaLLMProvider()
    transport = _lines_response([], status_code=500)
    _patch_client(provider, transport)

    with pytest.raises(RuntimeError, match="500"):
        async for _ in provider.chat_stream(messages=[]):
            pass


async def test_chat_stream_includes_tools_in_payload_when_given():
    provider = OllamaLLMProvider()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    _patch_client(provider, transport)

    tools = [{"type": "function", "function": {"name": "search"}}]
    async for _ in provider.chat_stream(messages=[], tools=tools):
        pass

    assert captured["body"]["tools"] == tools
    assert captured["body"]["stream"] is True


async def test_chat_stream_omits_tools_key_when_not_given():
    provider = OllamaLLMProvider()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    _patch_client(provider, transport)

    async for _ in provider.chat_stream(messages=[]):
        pass

    assert "tools" not in captured["body"]
